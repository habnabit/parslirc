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
message = prefix:prefix command:command params:params -> IRCLine._make(prefix + (command, params))
line = message:message lineEnd -> receiver.receivedLine(message)

initial = line

"""

tagKeyCharacters = set(string.letters + string.digits + '-/')


IRCLine = collections.namedtuple('IRCLine', 'tags prefix command params')
bindings = dict(IRCLine=IRCLine, tagKeyCharacters=tagKeyCharacters)


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

    def join(self, channels, keys=''):
        self.sendCommand('JOIN', [channels, keys])

    def leave(self, target, reason=''):
        self.sendCommand('PART', [target, reason])

    def quit(self, message=''):
        self.sendCommand('QUIT', [message])

    def names(self, channel):
        self.sendCommand('NAMES', [channel])

    def privmsg(self, target, message):
        self.sendCommand('PRIVMSG', [target, message])


class NullIRCReceiver(object):
    nickname = 'parslirc'
    username = 'parslirc'
    realname = 'parslirc'
    password = None

    capExtensions = []

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

    def unknownCTCP(self, line, command, params):
        pass

    def joined(self, line, channel):
        pass

    def userJoined(self, line, user, channel):
        pass

    def left(self, line, channel, reason):
        pass

    def userLeft(self, line, user, channel, reason):
        pass

    def userQuit(self, line, user, message):
        pass

    def privmsg(self, line, user, target, message):
        pass

    def action(self, line, user, target, message):
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


class CTCPDispatcher(WrapperBase):
    def irc_PRIVMSG(self, line):
        message = line.params[1]
        if not (message.startswith('\x01') and message.endswith('\x01')):
            return self.w.irc_PRIVMSG(line)
        command, _, arguments = message[1:-1].partition(' ')
        handler = getattr(self.w, 'ctcp_' + command.upper(), None)
        if handler is None:
            self.w.unknownCTCP(line, command, arguments)
        else:
            handler(line, arguments)


class BaseIRCFunctionality(WrapperBase):
    def connectionMade(self):
        self.w.sender.sendInitialGreeting(
            self.w.nickname, self.w.username, self.w.realname, self.w.password)
        self.w.connectionMade()

    def irc_PING(self, line):
        self.w.sender.sendCommand('PONG', line.params)

    def irc_001(self, line):
        self.w.signedOn()

    def irc_JOIN(self, line):
        user = IRCUser.fromFull(line.prefix)
        if user.nick == self.nickname:
            self.w.joined(line, line.params[0])
        else:
            self.w.userJoined(line, user, line.params[0])

    def irc_PART(self, line):
        user = IRCUser.fromFull(line.prefix)
        if user.nick == self.nickname:
            self.w.left(line, line.params[0])
        else:
            self.w.userLeft(line, user, line.params[0])

    def irc_NICK(self, line):
        user = IRCUser.fromFull(line.prefix)
        if user.nick == self.nickname:
            self.nickname = line.params[0]
            self.w.nickChanged(line, line.params[0])
        else:
            self.w.userRenamed(line, user, line.params[0])

    def irc_QUIT(self, line):
        self.w.userQuit(line, IRCUser.fromFull(line.prefix), line.params[0])

    def irc_PRIVMSG(self, line):
        self.w.privmsg(
            line, IRCUser.fromFull(line.prefix), line.params[0],
            line.params[1])

    def ctcp_ACTION(self, line, arguments):
        self.w.action(
            line, IRCUser.fromFull(line.prefix), line.params[0], arguments)


class CAPNegotiator(WrapperBase):
    def connectionMade(self):
        self.w.sender.sendLine('CAP LS')
        self.w.connectionMade()

    def irc_CAP(self, line):
        if line.params[1] == 'LS':
            supported = set(line.params[2].split())
            toRequest = supported.intersection(self.w.capExtensions)
            if toRequest:
                self.w.sender.sendCommand('CAP', ['REQ', ' '.join(toRequest)])
            else:
                self.w.sender.sendLine('CAP END')
        elif line.params[1] == 'ACK':
            print line
            self.w.sender.sendLine('CAP END')
        else:
            self.w.unknownCommand(line)


IRCClient = parsley.makeProtocol(
    ircGrammar,
    IRCSender,
    parsley.stackReceivers(NullIRCReceiver, BaseIRCFunctionality, IRCDispatcher),
    bindings)
