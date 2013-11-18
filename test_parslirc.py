import unittest

from twisted.test.proto_helpers import StringTransport

import parsley
import parslirc
import pytest


parslircGrammar = parslirc.ircParser

@pytest.fixture
def transport():
    transport = StringTransport()
    transport.abortConnection = lambda: None
    return transport


def stringParserFromRule(rule):
    def parseString(s, *a, **kw):
        return getattr(parslircGrammar(s), rule)(*a, **kw)
    return parseString

def test_params_parsing():
    parse = stringParserFromRule('params')

    assert parse('') == []
    assert parse('spam') == ['spam']
    assert parse('spam eggs') == ['spam', 'eggs']
    assert parse(':spam') == ['spam']
    assert parse('spam :eggs') == ['spam', 'eggs']
    assert parse('spam eggs :more spam') == ['spam', 'eggs', 'more spam']
    assert parse(':long spam') == ['long spam']
    assert parse(': space after colon') == [' space after colon']

def test_tag_parsing():
    parse = stringParserFromRule('tag')

    assert parse('foo') == ('foo', None)
    assert parse('fO-0') == ('fO-0', None)
    assert parse('foo/fO-0') == ('foo/fO-0', None)
    assert parse('foo=bar') == ('foo', 'bar')
    assert parse('foo/fO-0=bar') == ('foo/fO-0', 'bar')
    assert parse('foo=bar:baz') == ('foo', 'bar:baz')

def test_tags_parsing():
    parse = stringParserFromRule('tags')

    assert parse('') == {}
    assert parse('@ ') == {}
    assert parse('@foo ') == {'foo': None}
    assert parse('@foo;bar ') == {'foo': None, 'bar': None}
    assert parse('@foo;bar=baz ') == {'foo': None, 'bar': 'baz'}
    assert parse('@foo=bar;baz ') == {'foo': 'bar', 'baz': None}
    assert parse('@foo=foo;bar=bar ') == {'foo': 'foo', 'bar': 'bar'}

def test_message_parsing():
    parse = stringParserFromRule('message')

    assert parse(':Angel PING') == ({}, 'Angel', 'PING', [])
    assert parse(':Angel PRIVMSG Wiz :Hello are you receiving this message ?') == (
        {}, 'Angel', 'PRIVMSG', ['Wiz', 'Hello are you receiving this message ?'])
    assert parse('@t=1319042451 :Angel PRIVMSG Wiz :Hello are you receiving this message ?') == (
        {'t': '1319042451'}, 'Angel', 'PRIVMSG', ['Wiz', 'Hello are you receiving this message ?'])

    parsed = parse('@t=1319042451 :Angel PRIVMSG Wiz :Hello are you receiving this message ?')
    assert parsed.tags == {'t': '1319042451'}
    assert parsed.prefix == 'Angel'
    assert parsed.command == 'PRIVMSG'
    assert parsed.params == ['Wiz', 'Hello are you receiving this message ?']

def test_prefixParam_parsing():
    parse = stringParserFromRule('prefixParam')

    assert parse('()') == {}
    assert parse('(ov)@+') == {'@': 'o', '+': 'v'}
    assert parse('(ovh)@+%') == {'@': 'o', '+': 'v', '%': 'h'}
    assert parse('(hov)%@+') == {'@': 'o', '+': 'v', '%': 'h'}
    with pytest.raises(parsley.ParseError):
        assert parse('(hov)%@+!')
    with pytest.raises(parsley.ParseError):
        assert parse('(hove)%@+')

def test_modes_parsing():
    parse = stringParserFromRule('modes')

    assert parse('+foo-bar') == [(True, 'f'), (True, 'o'), (True, 'o'), (False, 'b'), (False, 'a'), (False, 'r')]
    assert parse('+fo+o-b-ar') == [(True, 'f'), (True, 'o'), (True, 'o'), (False, 'b'), (False, 'a'), (False, 'r')]
    assert parse('+f+o+o-b-a-r') == [(True, 'f'), (True, 'o'), (True, 'o'), (False, 'b'), (False, 'a'), (False, 'r')]
    assert parse('+a-b+c-d') == [(True, 'a'), (False, 'b'), (True, 'c'), (False, 'd')]

def test_isupport_parsing():
    assert parslirc.parseISupport('FOO') == ('FOO', None)
    assert parslirc.parseISupport('FOO=bar') == ('FOO', ['bar'])
    assert parslirc.parseISupport('FOO=bar,baz') == ('FOO', ['bar', 'baz'])
    assert parslirc.parseISupport('FOO=a:b') == ('FOO', {'a': 'b'})
    assert parslirc.parseISupport('FOO=a:b,c:d') == ('FOO', {'a': 'b', 'c': 'd'})
    assert parslirc.parseISupport('FOO=a:b,c:d,x') == ('FOO', [('a', 'b'), ('c', 'd'), (None, 'x')])

def test_IRCUser():
    parsed = parslirc.IRCUser.fromFull('foo!bar@baz')
    assert parsed == ((), 'foo', 'bar', 'baz', 'foo!bar@baz')
    assert parsed.prefixes == ()
    assert parsed.nick == 'foo'
    assert parsed.user == 'bar'
    assert parsed.host == 'baz'
    assert parsed.full == 'foo!bar@baz'

    assert parslirc.IRCUser.fromFull('*!*@*') == ((), '*', '*', '*', '*!*@*')
    assert parslirc.IRCUser.fromFull('+foo!bar@baz', '@+') == (('+',), 'foo', 'bar', 'baz', '+foo!bar@baz')
    assert parslirc.IRCUser.fromFull('@+foo!bar@baz', '@+') == (('@', '+'), 'foo', 'bar', 'baz', '@+foo!bar@baz')

def test_ircSender_sendLine(transport):
    s = parslirc.IRCSender(transport)
    s.sendLine('spam eggs')
    assert transport.value() == 'spam eggs\r\n'
    s.sendLine('spam spam spam')
    assert transport.value() == 'spam eggs\r\nspam spam spam\r\n'

def test_ircSender_sendCommand(transport):
    s = parslirc.IRCSender(transport)

    s.sendCommand('spam', [])
    assert transport.value() == 'spam\r\n'
    transport.clear()

    s.sendCommand('spam', ['eggs'])
    assert transport.value() == 'spam :eggs\r\n'
    transport.clear()

    s.sendCommand('spam', ['spam', 'spam'])
    assert transport.value() == 'spam spam :spam\r\n'
    transport.clear()

    s.sendCommand('spam', ['spam', 'spam', 'spam spam spam'])
    assert transport.value() == 'spam spam spam :spam spam spam\r\n'
    transport.clear()

    with pytest.raises(ValueError):
        s.sendCommand('spam', ['eggs and spam', 'spam'])


def test_ircSender_setNick(transport):
    s = parslirc.IRCSender(transport)
    s.setNick('spam')
    assert transport.value() == 'NICK :spam\r\n'


def test_ircSender_sendInitialGreeting(transport):
    s = parslirc.IRCSender(transport)

    s.sendInitialGreeting('a', 'b', 'c')
    assert transport.value() == 'NICK :a\r\nUSER b b b :c\r\n'
    transport.clear()

    s.sendInitialGreeting('a', 'b', 'spam eggs')
    assert transport.value() == 'NICK :a\r\nUSER b b b :spam eggs\r\n'
    transport.clear()

    s.sendInitialGreeting('a', 'b', 'spam eggs', 'eggs spam')
    assert transport.value() == 'PASS :eggs spam\r\nNICK :a\r\nUSER b b b :spam eggs\r\n'


class FakeDispatchee(object):
    def __init__(self):
        self.commands = []

    def irc_SPAM(self, line):
        self.commands.append(('spam', line))

    def irc_EGGS(self, line):
        self.commands.append(('eggs', line))

    def unknownCommand(self, line):
        self.commands.append(('unknown', line))

def test_IRCDispatcher():
    fake = FakeDispatchee()
    d = parslirc.IRCDispatcher(fake)
    d.receivedLine(parslirc.IRCLine({}, 'spam.freenode.net', 'SPAM', ['eggs']))
    d.receivedLine(parslirc.IRCLine({}, 'eggs.freenode.net', 'EGGS', ['spam']))
    d.receivedLine(parslirc.IRCLine({}, 'spam-eggs.freenode.net', 'SPAMEGGS', []))
    assert fake.commands == [
        ('spam', ({}, 'spam.freenode.net', 'SPAM', ['eggs'])),
        ('eggs', ({}, 'eggs.freenode.net', 'EGGS', ['spam'])),
        ('unknown', ({}, 'spam-eggs.freenode.net', 'SPAMEGGS', [])),
    ]


class FakeBaseIRCFunctionalityWrapped(object):
    nickname = 'a'
    username = 'b'
    realname = 'spam eggs'
    password = None

    def __init__(self, sender):
        self.sender = sender
        self.hasConnected = False
        self.hasSignedOn = False

    def connectionMade(self):
        self.hasConnected = True

    def signedOn(self):
        self.hasSignedOn = True

class BaseIRCFunctionalityTestCase(unittest.TestCase):
    def setUp(self):
        self.transport = transport()
        self.sender = parslirc.IRCSender(self.transport)
        self.fake = FakeBaseIRCFunctionalityWrapped(self.sender)
        self.funct = parslirc.BaseIRCFunctionality(self.fake)

    def test_ping(self):
        self.funct.irc_PING(parslirc.IRCLine({}, 'irc-server', 'PING', ['nonce']))
        assert self.transport.value() == 'PONG :nonce\r\n'

    def test_signedOn(self):
        assert not self.fake.hasSignedOn
        self.funct.irc_001(parslirc.IRCLine({}, 'irc-server', '001', ['yo']))
        assert self.fake.hasSignedOn

    def test_connectionMade(self):
        assert not self.fake.hasConnected
        self.funct.connectionMade()
        assert self.fake.hasConnected
        assert self.transport.value() == 'NICK :a\r\nUSER b b b :spam eggs\r\n'
