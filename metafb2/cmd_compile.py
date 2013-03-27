"""
"""

import optparse
import codecs
import os.path
from lxml import etree
from base64 import b64encode as base64_encode
from .print_ext import print_err
from . import project
from . import markup
from .xml import NSMAP
from .xml import XLINK_NAMESPACE
from .xml import append_element
from .xml import append_element_cond
from .xml import append_author_element
from .xml import make_id


class OptionParser(optparse.OptionParser):
    def __init__(self):
        optparse.OptionParser.__init__(self, usage="%prog compile [OPTIONS] <PROJECT_FILE>")
        self.add_option("-o", "--output", dest="out_filename", 
                        help="write generated FictionBook XML to FILE", metavar="FILE")

def format_author(a):
    if "nickname" in a and a['nickname'] is not None:
        return a['nickname']
    
    components = list()
    for c in ("first-name", "middle-name", "last-name"):
        if c in a and a[c] is not None:
            components.append(a[c])
            
    return " ".join(components)

def action(cmd_args):
    parser = OptionParser()
    (options, args) = parser.parse_args(args=cmd_args)
    
    if options.out_filename is None:
        options.out_filename = "result.fb2"

    if len(args) > 1:
        print_err("there must just one PROJECT_FILE")
        exit(1)
     
    project_props, authors, translators, doc_authors, doc_history, genres, book_sequences = project.parse_project_file(args[0])
    
    root = etree.Element("FictionBook", nsmap=NSMAP)
    desc = append_element(root, "description")
    title_info = append_element(desc, "title-info")
    for g in genres:
        append_element(title_info, "genre", g)
        
    for a in authors:
        append_author_element(title_info, "author", a)
        
    append_element(title_info, "book-title", project_props['book-title'])
    if project_props['annotation-file'] is not None:
        ann = markup.translate_annotation(project_props['annotation-file'])
        if len(list(ann)) != 0:
            title_info.append(ann)
        
    append_element_cond(title_info, "date", project_props['date'], {'value': project_props['date']})
    cover_image_name = None
    if project_props['cover-image'] is not None:
        cover_image_name = project_props['cover-image']
        cover = append_element(title_info, "coverpage")
        coverimage = append_element(cover, "image")
        coverimage.set("{%s}href" % XLINK_NAMESPACE, "#%s" % base64_encode(cover_image_name))
        # set value later
        
    append_element_cond(title_info, "lang", project_props['lang'])
    append_element_cond(title_info, "src-lang", project_props['src-lang'])
    for t in translators:
        append_author_element(title_info, "translator", t)
        
    for s in book_sequences:
        append_element(title_info, "sequence", None, attrs=s)
    
    # fill document info section
    doc_info = append_element(desc, "document-info")
    for a in doc_authors:
        node = append_element(doc_info, "author")
        for k in ('first-name', 'middle-name', 'last-name', 'nickname', 'home-page', 'email'):
            if a[k] is not None:
                append_element(node, k, a[k])

    append_element_cond(doc_info, "program-used", project_props['program-used'])
    append_element_cond(doc_info, "date", project_props['doc-date'], {'value': project_props['doc-date']})
    append_element_cond(doc_info, "src-ocr", project_props['src-ocr'])
    append_element(doc_info, "id", project_props['book-id'])
    append_element_cond(doc_info, "version", project_props['book-version'])
    
    if len(doc_history) > 0:
        node = append_element(doc_info, "history")
        for v,t in doc_history:
            append_element(node, "p", "%s : %s" % (v, t))
    
    # fill publish-info section
    publ_info = append_element(desc, "publish-info")
    append_element_cond(publ_info, "book-name", project_props['book-name'])
    append_element_cond(publ_info, "publisher", project_props['publisher'])
    append_element_cond(publ_info, "city", project_props['publish-city'])
    append_element_cond(publ_info, "year", project_props['publish-year'])
    append_element_cond(publ_info, "isbn", project_props['publish-isbn'])
    
    #body = append_element(root, "body")
    #append_element(body, "section")
    
    body, images, notes_map = markup.translate_body(project_props['content-file'])
    root.append(body)
    
    # prepare book title
    title = markup.fbe("title")
    # append authors list
    authors_list = [format_author(a) for a in authors]
    title.append(markup.pprocess("p", ", ".join(authors_list)))

    # append book title
    title.append(markup.pprocess("p", project_props['book-title']))
    body.insert(0, title)
    
    body.insert(0, title)

    # process notes
    if project_props['notes-file'] is not None:
        notes_file = project_props['notes-file']
        if not os.path.isfile(notes_file):
            raise markup.InvalidMarkupError("Notes files not found")
        #notes_body, notes_images = markup.translate_body(notes_file)
        notes_images, notes_sections = markup.translate_notes(notes_file)
        # notes_sections - dict, key is note_id
        
        all_note_ids = notes_sections.keys()
        # notes_map.keys() - list of all notes in the text
        # all_notes - list of all notes id
        for note_id in notes_map.keys():
            if note_id not in all_note_ids:
                raise markup.InvalidMarkupError("Note id `%s' declared but not defined" % note_id)
        

        # form list of notes that should be included into result file
        rev_notes_map = dict()
        for k,v in notes_map.iteritems():
            if v in rev_notes_map:
                raise markup.InvalidMarkupError("Each note MUST occur just once!")
            
            rev_notes_map[v] = k
        
        notes_body = markup.fbe("body")
        notes_body.set("name", "notes")
        root.append(notes_body)

        for k in sorted(rev_notes_map.keys()):
            note_id = rev_notes_map[k]
            notes_sections[note_id].sx_title.clear()
            notes_sections[note_id].sx_title.append(markup.fbe("p", str(k)))
            notes_body.append(notes_sections[note_id].sx)
            
        
        images = images.union(notes_images)
    
    if cover_image_name is not None:
        images.add(cover_image_name)
    
    for img in images:
        img_path = os.path.join(project_props['images-path'], img)
        img_id = make_id(img)
        if not os.path.isfile(img_path):
            raise markup.InvalidMarkupError("Picture file `%s' not found." % img_path)
        # encode img file
        f = open(img_path, "rb")
        b = base64_encode(f.read())
        f.close()
        
        img_name_lo = img.lower()
        content_type = None
        if img_name_lo.endswith(".jpg"):
            content_type = "image/jpeg"
        elif img_name_lo.endswith(".png"):
            content_type = "image/png"
        elif img_name_lo.endswith(".gif"):
            content_type = "image/gif"
        else:
            raise markup.InvalidMarkupError("Unknown picture `%s' format." % img)
        
        
        bin = append_element(root, "binary", b, attrs={'id': img_id, 'content-type': content_type})
        root.append(bin)
        
    #if project_props['cover-image'] is not None and project_props['cover-image'] not in images:
    #    bin = append_element(root, "binary", b, attrs={'id': 'img_%04d' % img_id, 'content-type': content_type})
    
    outf = codecs.open(options.out_filename, mode="w", encoding="utf-8")
    outf.write('<?xml version="1.0" encoding="utf-8"?>\n')
    outf.write(etree.tostring(root, pretty_print=True, xml_declaration=False, encoding=unicode))
    outf.close()