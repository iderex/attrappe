# Security policy

## Reporting a problem

Report privately, through GitHub's private vulnerability reporting on this
repository, at
<https://github.com/iderex/attrappe/security/advisories/new>. That channel is
enabled and it is the first channel. Do not open a public issue for a suspected
vulnerability, because an issue is readable by everyone from the moment it is
filed.

If private reporting is unavailable to you for any reason, open a public issue
saying only that you have a report to make and asking for a private channel.
Say nothing about the problem itself in it.

## What to expect

This project is maintained by one person alongside other work, so the honest
answer about timing is a short one.

A report will be acknowledged when it is read. No acknowledgement deadline is
promised, because a deadline this project cannot keep is worse than no deadline:
a reporter who is told to expect an answer within a stated time and does not get
one is left guessing whether the report arrived at all.

You will be told which of these applies once the report has been looked at:
the behaviour is a defect and will be fixed, the behaviour is a defect and will
not be fixed, or the behaviour is outside what this project's design assumes and
is described in the threat model below. The third answer is a real answer and it
is not a dismissal.

No bounty is offered. Credit in the advisory and in the release notes is offered
and is yours to decline.

## Supported versions

There has been no release. Until there is one, the supported version is the
current mainline and nothing else, and there is no branch on which a fix would be
backported.

When a release exists, what is supported and for how long is stated here rather
than assumed, and the version policy behind it is #55.

## Threat model

This software is a network listener with no authentication. It parses text that
an attacker controls and it can load and execute profiles supplied as code. It is
intended to run on loopback, in a test environment, against instrument-control
software that is being tested. It is not hardened for anything else, and the
paragraphs below say so rather than implying a defence it does not have.

Three surfaces.

The listener accepts connections and has no authentication, no authorisation and
no transport security. Anything that can reach the port can drive the emulated
instrument. The default binding is loopback, which is a default and not a
control: an operator who binds it to another interface has put an unauthenticated
service on that interface, and nothing in the software stops them.

The parser is the one surface that takes untrusted input by design, and it is
the place to look first. Every byte a client sends reaches it, before any
authentication because there is none, and it does the most work of anything in
this project on data it did not choose. A report about the parser is the report
most likely to be about a real defect.

A device profile can carry a Python module, and loading a profile executes that
module. That is stated in `docs/decisions/0005-profiles.md` and it is a design
decision rather than an oversight. There is no sandbox. A profile from a source
you do not trust is code from a source you do not trust, and the safe handling of
it is the same as for any other program you were sent.

Deployment beyond loopback in a test environment is outside what the design
assumes. That is not a warning that such a deployment is merely discouraged. It
means the software was built without the controls such a deployment needs, and
adding them is not a configuration change.

## What counts as a report worth sending

A defect in the parser, in the listener or in the profile loader that a client on
the port can trigger. A way to make the emulator affect the host beyond the files
an operator pointed it at. A dependency advisory that reaches this project.

The absence of authentication is not a report. It is written above, it is
deliberate, and there is nothing to fix in it.
