"""
Markup parsing functions.
"""
from lxml import etree
from .xml import NSMAP
from .xml import XLINK_NAMESPACE
from .xml import TEXT_XML_TEMPLATE
from .xml import append_element
from .xml import append_element_cond
from .xml import make_id
from . import print_ext
from .linestream import LineStream
import codecs
import re


toHex = lambda x:"".join([hex(ord(c))[2:].zfill(2) for c in x])

class InvalidMarkupError(BaseException):  pass
class UnexpectedElementError(BaseException):  pass

def fbe(tag, text=None, attrs=None):
    """
    Create new FB2 xml element
    """
    if attrs is None:
        attrs = dict()
        
    node = etree.Element(tag, nsmap=NSMAP)
    if text is not None:
        node.text = text
    
    for k,v in attrs.items():
        node.set(k, v)
        
    return node

last_note_num = 1
notes_map = dict()

REF_RE = re.compile("{{([^}]+?)}}")
STRONG_RE = re.compile("\*\*(.+?)\*\*")
EMPHASIS_RE = re.compile("//(.+?)//")
def pprocess(tag, text):
    """
    Process text and return xml elements for converted text
    """
    global last_note_num
    text = text.replace("&", "&#38;").replace("<", "&#60;").replace(">", "&#62;")
    
    mo = REF_RE.search(text)
    while mo is not None:
        note_id = mo.group(1)
        text = REF_RE.sub(u'<a l:href="#%s" type="note">[%d]</a>' % 
                          (make_id(note_id), last_note_num), text, 1)
        notes_map[note_id] = last_note_num
        last_note_num += 1
        mo = REF_RE.search(text)
    
    text = REF_RE.sub('<a l:href="#\\1" type="note">[%d]</a>' % last_note_num, text)
    text = STRONG_RE.sub("<strong>\\1</strong>", text)
    text = EMPHASIS_RE.sub("<emphasis>\\1</emphasis>", text)

    # perform some "back" replacement
    text = text.replace("&#60;sup&#62;", "<sup>").replace("&#60;/sup&#62;", "</sup>")\
        .replace("&#60;sub&#62;", "<sub>").replace("&#60;/sub&#62;", "</sub>")
    
    xml = TEXT_XML_TEMPLATE % {
        'text': text,
        'tag': tag
        }
    try:
        root = etree.fromstring(xml)
    except etree.XMLSyntaxError, e:
        print xml
        raise
    
    return root

"""
metafb2 body grammar.

Document MUST start with 1st level SECTION element ("^= ")
"""

def skip_empty_lines(f):
    """
    Skip empty lines and comments.
    """
    while True:
        try:
            line = f.next()
        except StopIteration:
            break
        
        if line != "" and not line.startswith("#"):
            f.go(-1)
            break

class Section:
    def __init__(self):
        self.lines = list()
        self.subsections = list()
        self.parent = None
        self.sx = None
        self.images = set()
        self.addr = 0 # position of first line of section
        self.id = None
        
    def append_section(self, s):
        self.subsections.append(s)
        s.set_parent(self)
        
    def set_parent(self, parent):
        self.parent = parent
        
    def current_offset(self):
        if not isinstance(self.lines, LineStream):
            return None
        
        return self.addr + self.lines.pos() + 1

SECTION_RE = re.compile("^(=+) *(.+)?$")
def split_into_sections(f):
    """
    Split lines into the sections tree
    """
    root = Section()
    
    current_section = Section()
    current_section_level = 1
    # Do not append to the root!
    # root.append(current_section)
    current_section.set_parent(root)
    
    is_header_block = False
    
    while True:
        try:
            line = f.next()
        except StopIteration:
            break
        
        mo = SECTION_RE.match(line)
        if mo is not None:
            # create new section
            new_section_level = len(mo.group(1))
            if is_header_block and new_section_level == current_section_level:
                # do not create new section, just add line to the current
                current_section.lines.append(line)
                continue
            
            new_section = Section()
            new_section.lines.append(line)
            new_section.addr = f.pos()
            new_section_level = len(mo.group(1))
            # find position of this section on the tree
            
            if new_section_level <= current_section_level:
                parent = current_section.parent
                for x in range(0, current_section_level-new_section_level):
                    parent = parent.parent
                    
                # append section after the current section
                parent.append_section(new_section)
                is_header_block = True
            elif new_section_level > current_section_level:
                if new_section_level > current_section_level+1:
                    raise InvalidMarkupError("Sections must be directly nested")
                # new section is a subsection of current_section
                current_section.append_section(new_section)
                is_header_block = True
                
            current_section = new_section
            current_section_level = new_section_level
            continue
        
        is_header_block = False
        # add line to current section lines list
        current_section.lines.append(line)
        
    return root

def skip_empty_lines(f):
    """
    Skip empty lines and comments.
    """
    while True:
        line = f.next()
        
        if line != "" and not line.startswith("#"):
            f.go(-1)
            break

ID_RE = re.compile("^@id: *(.+)$")
def process_id(f):
    """
    @return: id value or None if there is no one
    """
    line = f.next()

    mo = ID_RE.match(line)
    if mo is None:
        f.go(-1)
        return None
    
    return mo.group(1)

def process_para(f):
    """
    Process paragraph element
    
    @return: paragraph xml element or None
    """
    skip_empty_lines(f)
    pos = f.pos()
    text_lines = list()
    
    while True:
        try:
            line = f.next()
        except StopIteration:
            break
        
        if line.startswith("#"):
            continue
        
        if line == "" or line.startswith("@") or line.startswith("="):
            f.go(-1)
            # finish block
            break
        
        text_lines.append(line)
        
    if len(text_lines) == 0:
        return None
    
    return pprocess("p", " ".join(text_lines))

EPIGRAPH_BEGIN_RE = re.compile("^@e$")
EPIGRAPH_END_RE = re.compile("^@e/(.+)?$")
def process_epigraph(f):
    """
    @return: xml element <epigraph> or None if there is no such element
    """
    skip_empty_lines(f)
    pos = f.pos()
    line = f.next()
    mo = EPIGRAPH_BEGIN_RE.match(line)
    if mo is None:
        f.seek(pos)
        return None
    
    epigraph = fbe("epigraph")
    
    block_end_reached = False
    try:
        while True:
            line = f.next()
            mo = EPIGRAPH_END_RE.match(line)
            if mo is not None:
                block_end_reached = True
                if mo.group(1) is not None:
                    epigraph.append(pprocess("text-author", mo.group(1)))
                break
            else:
                f.go(-1)
            
            
            # empty line
            el = process_empty_line(f)
            if el is not None:
                epigraph.append(el)
            # p - paragraph, must stand at the bottom of list
            p = process_para(f)
            if p is not None:
                epigraph.append(p)
            
    except StopIteration:
        pass
    
    if not block_end_reached:
        raise InvalidMarkupError("Epigraph block not closed.")
    
    return epigraph

ANN_BEGIN_RE = re.compile("^@ann$")
ANN_END_RE = re.compile("^@ann/$")
def process_ann(f):
    skip_empty_lines(f)
    line = f.next()
    mo = ANN_BEGIN_RE.search(line)
    if mo is None:
        f.go(-1)
        return None
    
    ann = fbe("annotation")
    
    block_end_reached = False
    try:
        while True:
            line = f.next()
            mo = ANN_END_RE.match(line)
            if mo is not None:
                block_end_reached = True
                break
            else:
                f.go(-1)

            # cite
            cite = process_cite(f)
            if cite is not None:
                ann.append(cite)

            # subtitle
            subtitle = process_subtitle(f)
            if subtitle is not None:
                ann.append(subtitle)

            # empty line
            el = process_empty_line(f)
            if el is not None:
                ann.append(el)
            # p - paragraph, must stand at the bottom of list
            p = process_para(f)
            if p is not None:
                ann.append(p)
            
    except StopIteration:
        pass

    if not block_end_reached:
        raise InvalidMarkupError("Annotation block not closed.")
    
    return ann
    
POEM_BEGIN_RE = re.compile("^@poem$")
POEM_END_RE = re.compile("@poem/(.+)?")
def process_poem(f):
    skip_empty_lines(f)
    pos = f.pos()
    line = f.next()
    mo = POEM_BEGIN_RE.search(line)
    if mo is None:
        f.go(-1)
        return None
    
    poem = fbe("poem")
    current_stanza = fbe("stanza")
    poem.append(current_stanza)
    
    block_end_reached = False
    try:
        while True:
            line = f.next()
            mo = POEM_END_RE.search(line)
            if mo is not None:
                block_end_reached = True
                if mo.group(1) is not None:
                    poem.append(pprocess("text-author", mo.group(1)))
                break
            
            if line == "":
                # close stanza and create stanza
                current_stanza = fbe("stanza")
                poem.append(current_stanza)
                continue
            
            current_stanza.append(pprocess("v", line))
            
    except StopIteration:
        pass
    
    if not block_end_reached:
        raise InvalidMarkupError("Poem block not closed.")
    
    return poem

CITE_BEGIN_RE = re.compile("^@cite$")
CITE_END_RE = re.compile("^@cite/(.+)?")
def process_cite(f):
    skip_empty_lines(f)
    pos = f.pos()
    line = f.next()
    mo = CITE_BEGIN_RE.match(line)
    if mo is None:
        f.go(-1)
        return None
    
    cite = fbe("cite")

    # now find inner citation elements: p, subtitle, empty-line
    block_end_reached = False
    
    try:
        while True:
            line = f.next()
            mo = CITE_END_RE.match(line)
            if mo is not None:
                block_end_reached = True
                text_author = mo.group(1)
                if text_author is not None:
                    cite.append(pprocess("text-author", text_author))
                break
            else:
                f.go(-1)

            # subtitle
            subtitle = process_subtitle(f)
            if subtitle is not None:
                cite.append(subtitle)
                continue
            # empty line
            el = process_empty_line(f)
            if el is not None:
                cite.append(el)
                continue
            # p - paragraph, must stand at the bottom of list
            para = process_para(f)
            if para is not None:
                cite.append(para)
    except StopIteration:
        pass

    if not block_end_reached:
        raise InvalidMarkupError("Cite block not closed.")
    
    return cite

IMAGE_RE = re.compile("^@img:(.*)$")
def process_image(f):
    """
    @return: tuple (image, image_name), where image is xml element, image_name is an image name.
    """
    skip_empty_lines(f)
    line = f.next()
    mo = IMAGE_RE.match(line)
    if mo is None:
        f.go(-1)
        return None, None
    
    image_name = mo.group(1)

    if image_name == "":
        raise InvalidMarkupError("Missing image name on line %d" % (f.pos()+1))
    
    img_id = make_id(image_name)
    image = fbe("image")
    image.set("{%s}href" % XLINK_NAMESPACE, "#%s" % img_id)
    
    return image, image_name

SUBTITLE_RE = re.compile("^@s:(.*)$")
def process_subtitle(f):
    """
    @return: subtitle xml element
    """
    skip_empty_lines(f)
    line = f.next()
    mo = SUBTITLE_RE.match(line)
    if mo is None:
        f.go(-1)
        return None
    
    text = mo.group(1)
    if text == "":
        raise InvalidMarkupError("Missing subtitle text on line %d" % (f.pos()+1))
    
    subtitle = pprocess("subtitle", text)
    return subtitle

def process_empty_line(f):
    """
    @return: empty line xml element
    """
    skip_empty_lines(f)
    line = f.next()
    if line != "@empty-line":
        f.go(-1)
        return None
    
    return fbe("empty-line")

def process_section(section):
    
    section.lines = LineStream(section.lines)
    section.sx = fbe("section")

    # find section title
    title_items = list()
    while True:
        try:
            line = section.lines.next()
        except StopIteration:
            break
        
        mo = SECTION_RE.match(line)
        if mo is None:
            section.lines.go(-1)
            break
        
        if mo.group(2) is not None:
            title_items.append(mo.group(2))
    
    if len(title_items) > 0:
        title = fbe("title")
        section.sx_title = title
        section.sx.append(title)
        for t in title_items:
            title.append(pprocess("p", t))
    try:
        # find ID element
        id = process_id(section.lines)
        if id is not None:
            section.sx.set("id", make_id(id))
            
        # discover all epigraphs
        while True:
            epigraph = process_epigraph(section.lines)
            if epigraph is None:
                break
            section.sx.append(epigraph)
        
        # discover ann
        ann = process_ann(section.lines)
        if ann is not None:
            section.sx.append(ann)
        
        # discover image
        image, image_name = process_image(section.lines)
        if image is not None:
            section.sx.append(image)
            section.images.add(image_name)
            
        if len(section.subsections) > 0:
            def assert_forbidden():
                raise InvalidMarkupError("Section has subsections so inner elements are not allowed.")
        else:
            def assert_forbidden(): pass
            
        # now find inner section elements: p, image, subtitle, cite, empty-line
        while True:
            # image
            image, image_name = process_image(section.lines)
            if image is not None:
                assert_forbidden()
                section.sx.append(image)
                section.images.add(image_name)
                continue
            # subtitle
            subtitle = process_subtitle(section.lines)
            if subtitle is not None:
                assert_forbidden()
                section.sx.append(subtitle)
                continue
            # cite
            cite = process_cite(section.lines)
            if cite is not None:
                assert_forbidden()
                section.sx.append(cite)
                continue
            # poem
            poem = process_poem(section.lines)
            if poem is not None:
                assert_forbidden()
                section.sx.append(poem)
                continue
            # empty line
            el = process_empty_line(section.lines)
            if el is not None:
                assert_forbidden()
                section.sx.append(el)
                continue
                
            # now we don't expect any other commands (lines that start with "@")
            skip_empty_lines(section.lines)
            line = section.lines.next()
            section.lines.go(-1)
            if line.startswith("@"):
                raise InvalidMarkupError("Unknown command on line %s `%s'" % (section.current_offset(), line))
            
            # p - paragraph, must stand at the bottom of list
            para = process_para(section.lines)
            if para is not None:
                assert_forbidden()
                section.sx.append(para)
                
            #print section.addr+section.lines.pos() # addr of the section, relative position inside the section
    except StopIteration:
        pass
    
    # find other section elements
    #etree.dump(section.sx)
    # process section.lines
    # detect section title elements
    
    for subsection in section.subsections:
        process_section(subsection)
            
def translate_body(filename):
    """
    return tuple (body, images_list, notes_map)
    """
    global notes_map
    body = etree.Element("body", nsmap=NSMAP)
    images = set()
    notes_map = dict()
    
    cf = codecs.open(filename, mode="r", encoding="utf-8")
    f = LineStream(cf)
    cf.close()
    
    if f.len() > 0:
        line = f.next()
        f.go(-1)
        if not line.startswith("="):
            raise InvalidMarkupError("First line must specify 1st level section, file `%s'" % filename)
    
    #1. split text into sections
    root = split_into_sections(f)
    #2. process each section separately
    process_section(root)
    #3. find all images
    
    def _walk_images(s, im):
        [im.add(x) for x in s.images]
        
        for subs in s.subsections:
            _walk_images(subs, im)
    
    # collect images
    _walk_images(root, images)

    def _walk_sections(s):
        for x in s.subsections:
            s.sx.append(x.sx)
            _walk_sections(x)
            
    _walk_sections(root)
    
    for x in root.subsections:
        body.append(x.sx)
        
    #etree.dump(body)
        
    # build xml tree
    
    #_pp(root, 0)
    
    return body, images, notes_map

def translate_annotation(filename):
    cf = codecs.open(filename, mode="r", encoding="utf-8")
    f = LineStream(cf)
    cf.close()
    ann = etree.Element("annotation", nsmap=NSMAP)
    
    try:
        while True:
            # subtitle
            subtitle = process_subtitle(f)
            if subtitle is not None:
                ann.append(subtitle)
                continue
            # cite
            cite = process_cite(f)
            if cite is not None:
                ann.append(cite)
                continue
            # poem
            poem = process_poem(f)
            if poem is not None:
                ann.append(poem)
                continue
            # empty line
            el = process_empty_line(f)
            if el is not None:
                ann.append(el)
                continue
                
            # now we don't expect any other commands (lines that start with "@")
            skip_empty_lines(f)
            line = f.next()
            f.go(-1)
            if line.startswith("@"):
                raise InvalidMarkupError("UNknown command on line %s `%s'" % (f.pos()+1, line))
            
            # p - paragraph, must stand at the bottom of list
            para = process_para(f)
            if para is not None:
                ann.append(para)
    except StopIteration:
        pass
    
    return ann

def split_notes_into_sections(f):
    """
    @return: Section() object with all sections
    """
    root = Section()
    
    #raw_sections = list()
    current_section = Section()
    current_section.set_parent(root)
    # do not append current_section !!! 
    
    try:
        while True:
            line = f.next()
            
            mo = SECTION_RE.match(line)
            if mo is not None:
                # start new section
                section_level = len(mo.group(1))
                
                if section_level != 1:
                    raise InvalidMarkupError("In the notes file only first level sections allowed. Level: %s." % section_level)
                
                new_section = Section()
                new_section.addr = f.pos()
                root.append_section(new_section)
                current_section = new_section
                
                # find section id, element "@id" must follow section header
                mo = ID_RE.match(f.next())
                f.go(-1)
                if mo is None:
                    raise InvalidMarkupError("@id element is required for each section in the notes file!")
                current_section.id = mo.group(1)
                
            
            current_section.lines.append(line)
                
    except StopIteration:
        pass
    
    return root

def translate_notes(filename):
    """
    Translate notes file. Notes file consists of 1st level sections only. Each section must 
    have an id element, all ids must be unique. Section title is ignored. 
    @return: tuple(images, sections), sections is dict, keys are sections ids, values are section xml nodes
    """
    cf = codecs.open(filename, mode="r", encoding="utf-8")
    f = LineStream(cf)
    cf.close()
    images = set()
    
    root = split_notes_into_sections(f)
    process_section(root)
    
    sections = dict()
    
    for s in root.subsections:
        if s.id in root.subsections:
            raise InvalidMarkupError("Section's ids in the notes file must be unique!")
        
        sections[s.id] = s
        
    def _walk_images(s, im):
        [im.add(x) for x in s.images]
        
        for subs in s.subsections:
            _walk_images(subs, im)
    
    # collect images
    _walk_images(root, images)

    return (images, sections)

def _pp(root, level):
    """
    pretty print
    """
    indent = "    " * level
    lines_indent = " " * (level+1)
    for x in root.subsections:
        print "%s: %s" % (indent, x)
        for l in x.lines:
            print "%s %s" % (lines_indent, l)
        _pp(x, level+1)
    
