"""
XML related funtions and classes
"""
from lxml import etree
from base64 import b64encode as base64_encode
import codecs

FB2_NAMESPACE = "http://www.gribuser.ru/xml/fictionbook/2.0"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"
TEXT_XML_TEMPLATE = '<%%(tag)s xmlns="%s" xmlns:l="%s">%%(text)s</%%(tag)s>' % (FB2_NAMESPACE, XLINK_NAMESPACE)

NSMAP = {None : FB2_NAMESPACE, 'l': XLINK_NAMESPACE}

def append_element(e, tag, text=None, attrs=None):
    if attrs is None:
        attrs = dict()
        
    node = etree.SubElement(e, tag)
    if text is not None:
        node.text = text
    
    for k,v in attrs.items():
        node.set(k, v)
    
    return node

def append_element_cond(e, tag, text, attrs=None):
    node = None
    
    if text is not None:
        node = append_element(e, tag, text, attrs)

    return node

def append_author_element(e, tag, a):
    node = append_element(e, tag)
    for k in ('first-name', 'middle-name', 'last-name', 'nickname', 'home-page', 'email'):
        if a[k] is not None:
            append_element(node, k, a[k])
            
    return node

def make_id(s):
    if isinstance(s, unicode):
        s = s.encode("utf-8")
    return base64_encode(s, "-_").replace("=", "")
    