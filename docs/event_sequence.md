# OpenHTF Event Sequences

If you're trying to figure out when something happens during your test, look no
further:

1. `test_start`'s plugs are instantiated
1. `test_start` is run in a new thread
1. All plugs for the test are instantiated
1. Each phase node is run
    1. If the node is a subtest, each node is run until a FAIL_SUBTEST is
       returned by a phase.
    1. If the node is a branch, each node is run if the condition is met
    1. If the node is a sequence, each node is run
    1. If the node is a group, each of the groups sequences is run
    1. If the node is a phase descriptor, that phase is run
1. All plugs' `tearDown` function is called
1. All plugs are deleted
1. Test outcome is calculated as PASS or FAIL
1. Output callbacks are called

## Phase node execution

```
[PhaseNode]
 |
 +--[PhaseDescriptor]
 |
 +--[Checkpoint]
 |
 \--[PhaseCollection]
     |
     +--[PhaseSequence]
     |   |
     |   +--[PhaseBranch]
     |   |
     |   \--[Subtest]
     |
     \--[PhaseGroup]
```

`PhaseNode`s are the basic building block for OpenHTF's phase execution.  They
are a base class that defines a few basic operations that can get recursively
applied.  The `PhaseDescriptor` is the primary executable unit that wraps the
phase functions. `PhaseCollection` is a base class for a node that contains
multiple nodes.  The primary one of these is the `PhaseSequence`, which is a
tuple of phase nodes; each of those nodes is executed in order with nested
execution if those nodes are other collections.  `PhaseBranch`s are phase
sequences that are only run when the Diagnosis Result-based conditions are met.
`Checkpoint` nodes check conditions, like phase failure or a triggered
diagnosis; if that condition is met, they act as a failed phase. `PhaseGroup`s
are phase collections that have three sequences as described below.

### Recursive nesting

Phase collections allow for nested nodes where each nested level is handled with
recursion.

OpenHTF does not check for or handle the situation where a node is nested inside
itself.  The current collection types are frozen to prevent this from happening.

## Test error short-circuiting

A phase raising an exception won't kill the test, but will initiate a
terminal short-circuit. Phases are additionally terminal if they return
`htf.PhaseResult.STOP` or if they exceed their Phase timeout.

If a `test_start` phase is terminal, then the executor will skip to Plug
Teardown, where only the plugs initialized for `test_start` have their
`teardown` functions called.

In all cases with terminal phases, the Test outcome is ERROR for output
callbacks.

### PhaseGroups

`PhaseGroup` collections behave like contexts. They are entered if their
`setup` phases are all non-terminal; if this happens, the `teardown` phases are
guarenteed to run.  `PhaseGroup` collections can contain additional `PhaseGroup`
instances. If a nested group has a terminal phase, the outer groups will trigger
the same shortcut logic.

For terminal phases (or phases that return `FAIL_SUBTEST`) in a `PhaseGroup`,
* If the phase was in the `setup` sequence, then we do not run the rest of
  the `PhaseGroup`.
* If the phase was in the `main` sequence, then we do not run the rest of the
  `main` sequence and proceed to the `teardown` sequence of that `PhaseGroup`.
* If the phase was in the `teardown` sequence, the rest of the `teardown`
  sequence ndoes are run, but outer groups will trigger the shortcut logic.
  This also applies to all nested phase nodes.

NOTE: If a phase calls `os.abort()` or an equivalent to the C++
`die()` function, then the process dies and you cannot recover the results from
this, so try to avoid such behavior in any Python or C++ libraries you use.

### Subtests

`Subtest`s are Phase Sequences that allow phases to exit early, but continue on
with other phases.  A phase can indicate this by returning
`htf.PhaseResult.FAIL_SUBTEST` or with a checkpoint with that result as its
action.  The details of subtests are included in the output test record.

The rest of the phases in a subtest after the failing node will be processed as:

* Phase descriptors are all skipped.
* Branches are not run at all, as though their condition was evaluated as false.
* Groups entered after the failing node are entirely skipped, including their
  `teardown` sequences.
* Groups with the failing node in its `main` sequence will skip the rest of the
  `main` sequence, but will run the teardown phases.
* Groups with the failing node in its `setup` sequence will skip the rest of the
  setup phases and will record skips for the `main` and `teardown` sequences.
* Groups with the failing node in its `teardown` sequence will still run the
  rest of the `teardown` sequence.
* Sequences are recursively processed by these same rules.

Phase group teardowns are run properly when nested in a subtest.

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
