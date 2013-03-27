"""
"""

class LineStream:
    
    def __init__(self, f):
        """
        Initialize LineStream object with
        """
        self.__lines = list()
        for line in f:
            self.__lines.append(line.strip(" \r\n\t\x00"))
        
        self.__len = len(self.__lines)
        self.__pos = -1
            
    def next(self):
        """
        Read next line
        
        @return: string or None if there is no next item
        """
        if self.__pos == self.__len-1:
            #return None
            raise StopIteration
        
        self.__pos += 1
        return self.cur()
    
    #def range(self, begin, end):
    #    return self.__lines[begin:end]
    
    def cur(self):
        return self.__lines[self.__pos]
        
    def go(self, n):
        """
        Move internal pointer to `n' lines, could be relative
        """
        new_pos = self.__pos + n
        
        self.seek(new_pos)
    
    def pos(self):
        return self.__pos
    
    def len(self):
        return self.__len
    
    def seek(self, new_pos):
        if new_pos < -1 or new_pos >= self.__len-1:
            raise Exception
        
        self.__pos = new_pos
        
        