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


class IRCUser(collections.namedtuple('IRCUser', 'nick user host full')):
    @classmethod
    def fromFull(cls, full):
        nick, _, userhost = full.partition('!')
        user, _, host = userhost.partition('@')
        return cls(nick, user, host, full)


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

    def setNick(self, nickname):
        self.sendCommand('NICK', [nickname])

    def sendInitialGreeting(self, nick, username, realname, password=None):
        if password is not None:
            self.sendCommand('PASS', [password])
        self.setNick(nick)
        self.sendCommand('USER', [username, username, username, realname])


class NullIRCReceiver(object):
    nickname = 'parslirc'
    username = 'parslirc'
    realname = 'parslirc'

    def __init__(self, sender, parser):
        self.sender = sender
        self.parser = parser

    def connectionMade(self):
        pass

    def connectionLost(self, reason):
        pass

    def signedOn(self):
        pass

    def unknownCommand(self, line):
        pass


class WrapperBase(object):
    def __init__(self, wrapped):
        self.w = wrapped

    def __getattr__(self, attr):
        return getattr(self.w, attr)


class IRCDispatcher(WrapperBase):
    def receivedLine(self, line):
        handler = getattr(self.w, 'irc_' + line.command, self.w.unknownCommand)
        handler(line)


class BaseIRCFunctionality(WrapperBase):
    def connectionMade(self):
        self.w.sender.sendInitialGreeting(
            self.w.nickname, self.w.username, self.w.realname)
        self.w.connectionMade()

    def irc_PING(self, line):
        self.w.sender.sendCommand('PONG', line.params)

    def irc_001(self, line):
        self.w.signedOn()


IRCClient = parsley.makeProtocol(
    ircGrammar,
    IRCSender,
    parsley.stackReceivers(NullIRCReceiver, BaseIRCFunctionality, IRCDispatcher),
    bindings)
