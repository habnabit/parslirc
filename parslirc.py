import collections
import string

import parsley


ircGrammar = r"""

lineEnd = '\r' '\n'
space = ' '+
nonColon = anything:x ?(x != ':')
nonSpace = anything:x ?(x != ' ')
nonLineEnd = anything:x ?(x not in '\r\n')
command = <nonSpace+>

spaceDelimitedParams = (<nonColon nonSpace*>:param space? -> param)*
tailAsList = (':' <nonLineEnd*>)?:tail -> [tail] if tail is not None else []
params = space? spaceDelimitedParams:params tailAsList:tail -> params + tail

tagKey = <(anything:x ?(x in tagKeyCharacters))+>
tagValue = <(anything:x ?(x not in '\r\n; '))+>
tag = tagKey:key ( '=' tagValue
                 | -> None):value -> (key, value)
tagsBuilder = ( tag:tag (';' tag)*:tags -> [tag] + tags
              | -> [])
tags = ( '@' tagsBuilder:tags ' ' -> dict(tags)
       | -> {})

prefix = ( tags:tags ':' <nonSpace+>:prefix space -> (tags, prefix)
         | -> (None, None))
message = prefix:prefix command:command params:params -> _IRCLine._make(prefix + (command, params))
line = message:message lineEnd -> receiver.receivedLine(message)

initial = line

"""

tagKeyCharacters = set(string.letters + string.digits + '-/')


_IRCLine = collections.namedtuple('_IRCLine', 'tags prefix command params')
bindings = dict(_IRCLine=_IRCLine, tagKeyCharacters=tagKeyCharacters)


class IRCSender(object):
    def __init__(self, transport):
        self.transport = transport

    def sendLine(self, line):
        self.transport.write('%s\r\n' % (line,))

    def sendCommand(self, command, arguments):
        if not arguments:
            self.sendLine(command)
        elif len(arguments) == 1:
            self.sendLine('%s :%s' % (command, arguments[0]))
        else:
            if any(' ' in argument for argument in arguments[:-1]):
                raise ValueError('only the last argument can contain spaces')
            self.sendLine('%s %s :%s' % (
                command, ' '.join(arguments[:-1]), arguments[-1]))


class NullIRCReceiver(object):
    def __init__(self, sender, parser):
        self.sender = sender
        self.parser = parser

    def connectionMade(self):
        pass

    def connectionLost(self, reason):
        pass

    def receivedLine(self, message):
        raise message

IRCClient = parsley.makeProtocol(ircGrammar, IRCSender, NullIRCReceiver, bindings)
