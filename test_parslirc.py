from twisted.test.proto_helpers import StringTransport

import parsley
import parslirc
import pytest


parslircGrammar = parsley.makeGrammar(parslirc.ircGrammar, parslirc.bindings)

@pytest.fixture
def transport():
    transport = StringTransport()
    transport.abortConnection = lambda: None
    return transport


def stringParserFromRule(rule):
    def parseString(s):
        return getattr(parslircGrammar(s), rule)()
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

    assert parse(':Angel PRIVMSG Wiz :Hello are you receiving this message ?') == (
        {}, 'Angel', 'PRIVMSG', ['Wiz', 'Hello are you receiving this message ?'])
    assert parse('@t=1319042451 :Angel PRIVMSG Wiz :Hello are you receiving this message ?') == (
        {'t': '1319042451'}, 'Angel', 'PRIVMSG', ['Wiz', 'Hello are you receiving this message ?'])

def test_ircState(transport):
    p = parslirc.IRCClient()
    p.makeConnection(transport)
    p.dataReceived('@t=1319042451 :Angel PRIVMSG Wiz :Hello are you receiving this message ?\r\n')
