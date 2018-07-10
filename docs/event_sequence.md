# OpenHTF Event Sequences

If you're trying to figure out when something happens during your test, look no
further:

1. `test_start`'s plugs are instantiated
1. `test_start` is run in a new thread
1. All plugs for the test are instantiated
1. Each phase is run
1. The teardown phase is run
1. All plugs' `tearDown` function is called
1. All plugs are deleted
1. Test outcome is calculated as PASS or FAIL
1. Output callbacks are called

## Test error short-circuiting

A phase raising an exception won't kill the test, but will initiate a
terminal short-circuit. Phases are additionally terminal if they return
`htf.PhaseResult.STOP` or if they exceed their Phase timeout.

If a `test_start` phase is terminal, then the executor will skip to Plug
Teardown, where only the plugs initialized for `test_start` have their
`teardown` functions called.

`PhaseGroup` collections behave like contexts. They are entered if their
`setup` phases are all non-terminal; if this happens, the `teardown` phases are
guarenteed to run.  `PhaseGroup` collections can contain additional `PhaseGroup`
instances. If a nested group has a terminal phase, the outer groups will trigger
the same shortcut logic.

For terminal phases in a `PhaseGroup`,
* If the phase was a `PhaseGroup.setup` phase, then we skip the rest of the
  `PhaseGroup`.
* If the phase was a `PhaseGroup.main` phase, then we skip to the
  `PhaseGroup.teardown` phases of that `PhaseGroup`.
* If the phase was a `PhaseGroup.teardown` phase, the rest of the `teardown`
  phases are run, but outer groups will trigger the shortcut logic.

In all cases with terminal phases, the Test outcome is ERROR for output
callbacks.

NOTE: If a phase calls `os.abort()` or an equivalent to the C++
`die()` function, then the process dies and you cannot recover the results from
this, so try to avoid such behavior in any Python or C++ libraries you use.


## Test abortion short-circuiting

When you hit Ctrl-C to the process the following occurs:

* If we're running a `test_start` phase, a `PhaseGroup` setup phase, or a
  `PhaseGroup` main phase, the phase's thread is attempted to be killed. No
  other phases of these kinds are run.
* `PhaseGroup` teardown phases are still run unless a second Ctrl-C is sent.
* We then follow the same steps as in [Test error shirt-circuiting](
    #test-error-shirt-circuiting)
* All plugs are deleted.
* Test outcome is ABORTED for output callbacks.
