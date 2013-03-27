"""
Additional console output functions
"""

from sys import stderr

def print_err(msg):
    print >>stderr, u"ERROR:", msg
    
def print_warning(msg):
    print >>stderr, u"WARNING:", msg
