import os
import tempfile
import re
import sys_config
import zipfile
import datetime
import const
import zlib


###########################################################################
#
#    Tag class

class Tag:
    id = 0
    name = ""
    is_array = False
    array_size = 0
    value = 0
    valid = True
    address = 0
    offset = 0
    size = 0
    scope = ""
    type = 0
    description = ""

    # runtime
    hash = 0
    read_request = False
    write_request = False
    timestamp = 0

    #----------------------------------------------------------------------

    def __init__(self, name):
        self.name = name.lower()
        self.hash = zlib.crc32(self.name)

    #----------------------------------------------------------------------

    def __str__(self):
        s = "<Tag> id: %d, address: %d, is_array: %d, array_size: %d, offset: %d, size: %d, " % \
            (self.id, self.address, self.is_array, self.array_size, self.offset, self.size)

        s += "scope: %s, type: %s, name: %s, valid: %d, value: %s, description: %s" % \
            (self.scope, self.type, self.name, self.valid, self.value, self.description)

        return s

    #----------------------------------------------------------------------


###########################################################################
#
#    TagList class

class TagList:

    list = None

    #----------------------------------------------------------------------

    def __init__(self):
        self.clear()

    #----------------------------------------------------------------------

    def add(self, tag):
        self.list.append(tag)

    #----------------------------------------------------------------------

    def clear(self):
        self.list = []

    #----------------------------------------------------------------------

    def get_by_name(self, name):
        name = name.lower()
        hash = zlib.crc32(name)
        for tag in self.list:
            if tag.hash == hash:
                return tag
        return None

    #----------------------------------------------------------------------

    def count(self):
        return self.list.count()

    #----------------------------------------------------------------------


###########################################################################
#
#    Base class for CyBro communication

class Allocation:

    __path = ''
    __nad = 0
    tags = None
    file_transfer_timestamp = None

    #----------------------------------------------------------------------

    def __init__(self, nad):
        # normalize path name - on Win it will convert slashes to backslashes
        alloc_path = sys_config.AllocationDirectory

        # make absolute path
        alloc_path = os.path.abspath(alloc_path)

        # add slash at the end of the path
        if (len(alloc_path) != 0) and (alloc_path[len(alloc_path) - 1] != os.path.sep):
            alloc_path += os.path.sep

        self.__path = alloc_path
        self.__nad = nad

    #----------------------------------------------------------------------

    def __parse_alloc_file(self, s):
        lines = s.splitlines()

        for line in lines:
            line = line.rstrip()
            if len(line) != 0 and line[0] != ';':
                m = re.search("^(\w*)\s*(\w*)\s*(\w*)\s*(\w*)\s*(\w*)\s*(\w*)\s*(\w*)\s*([\w\.]*)\s*(.*)", line)

                try:
                    tag = Tag(m.group(8))
                    tag.address = int(m.group(1), 16)
                    tag.id = int(m.group(2), 16)
                    tag.array_size = int(m.group(3))
                    tag.is_array = tag.array_size > 1
                    tag.offset = int(m.group(4))
                    tag.size = int(m.group(5))
                    tag.scope = m.group(6)
                    tag.type = m.group(7)
                    tag.description = m.group(9)

                    # add offset for timers and counters
                    tag.address += tag.offset

                    # override tag size because of timer and counter fields
                    if tag.type == "bit":
                        tag.type = const.DataTypeBit
                        tag.size = 1
                    elif tag.type == "int":
                        tag.type = const.DataTypeInt
                        tag.size = 2
                    elif tag.type == "long":
                        tag.type = const.DataTypeLong
                        tag.size = 4
                    elif tag.type == "real":
                        tag.type = const.DataTypeReal
                        tag.size = 4
                    else:
                        tag.type = const.DataTypeNone

                    if tag.is_array:
                        for i in range(tag.array_size):
                            array_tag = Tag("%s[%d]" % (tag.name, i))
                            array_tag.address = tag.address  + i * tag.size
                            array_tag.id = tag.id
                            array_tag.offset = tag.offset
                            array_tag.size = tag.size
                            array_tag.scope = tag.scope
                            array_tag.type = tag.type
                            array_tag.description = tag.description
                            self.tags.add(array_tag)
                    else:
                        self.tags.add(tag)
                except:
                    pass

    #----------------------------------------------------------------------

    def __create_filename(self):
        return self.__path + "c%d.alc" % self.__nad

    #----------------------------------------------------------------------

    def clear(self):
        self.tags = TagList()

    #----------------------------------------------------------------------

    def delete_cached_file(self):
        filename = self.__create_filename()

        if os.path.exists(filename):
            os.remove(filename)

    #----------------------------------------------------------------------

    def read_from_file(self):
        filename = self.__create_filename()
        content = ""

        if os.path.exists(filename):
            f = file(filename)
            try:
                content = f.read()
            except:
                pass
            f.close()

        return content

    #----------------------------------------------------------------------

    def read(self):
        self.clear()
        self.__parse_alloc_file(self.read_from_file())

    #----------------------------------------------------------------------

    def get_file_transfer_timestamp(self):

        filename = self.__create_filename()

        if os.path.exists(filename):
            f = file(filename)
            line1 = f.readline()
            # second line should contain timestamp
            line2 = f.readline()
            f.close()

            try:
                m = re.search("^;(\d*)-(\d*)-(\d*)\s*(\d*):(\d*):(\d*)", line2)
                year = int(m.group(1))
                month = int(m.group(2))
                day = int(m.group(3))
                hh = int(m.group(4))
                mm = int(m.group(5))
                sec = int(m.group(6))
                self.file_transfer_timestamp = datetime.datetime(year, month, day, hh, mm, sec)
                return self.file_transfer_timestamp
            except:
                return None
        else:
            return None

    #----------------------------------------------------------------------

    def _unzip_alloc_file(self, s):
        try:
            temp_filename = tempfile.mktemp()

            f_out = file(temp_filename, "wb")
            f_out.write(s)
            f_out.flush()
            f_out.close()

            result = ""
            zipped = zipfile.ZipFile(temp_filename)
            files = zipped.namelist()
            if len(files) != 0:
                result = zipped.read(files[0])

            zipped.close()
            os.remove(temp_filename)
            return result
        except:
            return ""

    #----------------------------------------------------------------------

    def process_zipped_alloc(self, s, transfer_timestamp):
        data = self._unzip_alloc_file(s)

        if len(data) != 0:
            filename = self.__create_filename()
            f_out = file(filename, "wb")

            if (transfer_timestamp != None):
                lines = data.splitlines()
                lines.insert(1, ";%s" % transfer_timestamp)
                f_out.write("\r\n".join(lines))
            else:
                f_out.write(data)

            f_out.close()
            self.read()

    #----------------------------------------------------------------------
