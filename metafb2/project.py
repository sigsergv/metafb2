"""
Functions for parsing project file
"""

import codecs
import ConfigParser
import os.path
from .print_ext import print_err

class InvalidProjectError(BaseException):
    pass

def parse_project_file(filename):
    try:
        pf = codecs.open(filename, "r", encoding="utf8")
    except IOError, e:
        raise InvalidProjectError(str(e))
        
    config = ConfigParser.ConfigParser()
    config.readfp(pf)
    
    sections = config.sections()
    
    project_props = dict()
    book_props = dict()
    project_props_keys = ("content-file", "annotation-file", "images-path", "notes-file",
                          "book-title", "genres", 
                          "lang", "src-lang", "program-used", "date", "book-id", "book-version",
                          "cover-image", "src-ocr",
                          "doc-date", "book-name", "publisher", "publish-city", "publish-year", 
                          "publish-isbn", 
                          )
    book_props_keys = ()
    
    for k in project_props_keys:
        if config.has_option("Project", k):
            project_props[k] = config.get("Project", k)
        else:
            project_props[k] = None
    
    # check required keys
    req_keys = ("content-file", "book-title", "book-id")
    for k in req_keys:
        if project_props[k] is None:
            raise InvalidProjectError("Invalid project file: required key `Project/%s' not found" % k)
        
    # check that required files exists
    req_files = ("content-file", "annotation-file")
    for k in req_files:
        if project_props[k] is None:
            continue
        if not os.path.isfile(project_props[k]):
            raise InvalidProjectError("File `%s' required for key `Project/%s' not found." %
                                      (project_props[k], k))
            
    # get book authors
    authors = list()
    for section in sections:
        if section.startswith("Author/"):
            authors.append(process_author_section(config.items(section)))
    
    translators = list()
    for section in sections:
        if section.startswith("Translator/"):
            translators.append(process_author_section(config.items(section)))
    
    
    # get document authors
    doc_authors = list()
    for section in sections:
        if section.startswith("DocAuthor/"):
            doc_authors.append(process_author_section(config.items(section)))
            
            
    # get sequences
    book_sequences = list()
    for section in sections:
        if section.startswith("Sequence/"):
            item = dict()
            item['name'] = config.get(section, "name")
            if config.has_option(section, "number"):
                item['number'] = config.get(section, "number")
            book_sequences.append(item)
                
    # get document history
    doc_history = list()
    if config.has_section("History"):
        doc_history = config.items("History")
        
    
    genres = list()
    if config.has_option("Project", "genres"):
        genres = [x.strip() for x in config.get("Project", "genres").split(",")]
    
    book_title = project_props['book-title']
    
    pf.close()
    return (project_props, authors, translators, doc_authors, doc_history, genres, book_sequences)


def process_author_section(items):
    keys = ('first-name', 'middle-name', 'last-name', 'nickname', 'home-page', 'email')
    res = dict()
    for k in keys: res[k] = None
    
    # TODO: implement requirements checking
    for (k,v) in items:
        if k not in keys:
            raise InvalidProjectError("Author section must not contain key `%s'" % k)
        res[k] = v
        
    return res