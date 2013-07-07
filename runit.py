import sys

from twisted.internet.defer import Deferred
from twisted.internet.endpoints import clientFromString
from twisted.internet.protocol import Factory
from twisted.internet.task import react
from twisted.protocols import policies
from twisted.python import log

import parsley
import parslirc



class SpewingWrapper(parslirc.WrapperBase):
    capExtensions = ['znc.in/server-time']

    def signedOn(self):
        self.sender.join('#colontea')

    def unknownCommand(self, line):
        print line

    def unknownCTCP(self, line, command, params):
        print line, command, params


IRCClient = parsley.makeProtocol(
    parslirc.ircGrammar,
    parslirc.IRCSender,
    parsley.stackReceivers(
        parslirc.IRCDispatcher,
        parslirc.CTCPDispatcher,
        parslirc.CAPNegotiator,
        parslirc.BaseIRCFunctionality,
        SpewingWrapper,
        parslirc.NullIRCReceiver,
    ),
    parslirc.bindings)


class IRCClientFactory(Factory):
    protocol = IRCClient


def main(reactor, description):
    client = clientFromString(reactor, description)
    d = client.connect(policies.SpewingFactory(IRCClientFactory()))
    d.addCallback(lambda p: Deferred())
    return d

log.startLogging(sys.stderr)
react(main, sys.argv[1:])
