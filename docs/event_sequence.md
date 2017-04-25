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
short-circuit.

When a phase raises an exception or returns `htf.PhaseResult.STOP`:
* If the phase was `test_start`, then we skip to plug `tearDown`.
* If the phase wasn't `test_start`, then we skip to the teardown phase.
* Test outcome is ERROR for output callbacks.

NOTE: If a phase calls `os.abort()` or an equivalent to the C++
`die()` function, then the process dies and you cannot recover the results from
this, so try to avoid such behavior in any Python or C++ libraries you use.


## Test abortion short-circuiting

When you hit Ctrl-C or send SIGTERM to the process the following occurs:

* If we're running a phase, the phase's thread is attempted to be killed.
  `test_start` and `teardown` are both considered phases here.
* We then follow the same steps as in [Test error shirt-circuiting](
    #test-error-shirt-circuiting)
* All plugs are deleted
* Test outcome is ABORTED for output callbacks.
