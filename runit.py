import sys

from twisted.internet.defer import Deferred
from twisted.internet.endpoints import TCP4ClientEndpoint
from twisted.internet.protocol import Factory
from twisted.internet.task import react
from twisted.protocols import policies
from twisted.python import log

import parsley
import parslirc



class SpewingWrapper(parslirc.WrapperBase):
    def unknownCommand(self, line):
        print line


IRCClient = parsley.makeProtocol(
    parslirc.ircGrammar,
    parslirc.IRCSender,
    parsley.stackReceivers(
        parslirc.NullIRCReceiver,
        SpewingWrapper,
        parslirc.BaseIRCFunctionality,
        parslirc.IRCDispatcher,
    ),
    parslirc.bindings)


class IRCClientFactory(Factory):
    protocol = IRCClient


def main(reactor):
    client = TCP4ClientEndpoint(reactor, 'irc.freenode.net', 6667)
    d = client.connect(IRCClientFactory())
    d.addCallback(lambda p: Deferred())
    return d

react(main, [])
