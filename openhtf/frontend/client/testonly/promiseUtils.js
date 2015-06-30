/*
 * DO NOT DISTRIBUTE
 * This is copied from google3 minus minor changes for importing and jasmine 2.
 * We use it for testonly so it's more or less okay.
 * https://cs/depot/google3/javascript/angular/testing/promiseutils.js
 */
// Copyright 2013 Google Inc. All Rights Reserved.
'use strict';

var promiseUtils = {};

(function() {
/**
 * State of a $q promise.
 * @enum {string}
 */
promiseUtils.PromiseState = {
  PENDING: 'pending',
  RESOLVED: 'resolved',
  REJECTED: 'rejected'
};

/**
 * Result object holding success or error values when a promise is resolved.
 * @constructor
 * @export
 */
promiseUtils.PromiseResult = function() {
  this.value = null;
  /** @type {promiseUtils.PromiseState} */
  this.state = promiseUtils.PromiseState.PENDING;
};

/**
 * Helper function to capture result from the given promise when promise gets
 * resolved in success or error handlers.
 * @param {!angular.$q.Promise} promise Angular promise object.
 * @return {promiseUtils.PromiseResult} Object containing results
 *     when resolved.
 * @private
 */
promiseUtils.capturePromiseResult_ = function(promise) {
  var result = new promiseUtils.PromiseResult();
  promise.then(function(value) {
    result.value = value;
    result.state = promiseUtils.PromiseState.RESOLVED;
  }, function(value) {
    result.value = value;
    result.state = promiseUtils.PromiseState.REJECTED;
  });
  return result;
};

/**
 * Property name used to store capture stored result on a promise object.
 * @const
 * @private
 */
promiseUtils.PROMISE_RESULT_KEY_ = 'ngTestingPromiseUtilsResult';

/**
 * Captures promise result and stores it on promise itself.
 * @param {!angular.$q.Promise} promise Angular promise object.
 * @private
 */
promiseUtils.attachToPromiseOnce_ = function(promise) {
  if (!promise[promiseUtils.PROMISE_RESULT_KEY_]) {
    promise[promiseUtils.PROMISE_RESULT_KEY_] =
        promiseUtils.capturePromiseResult_(promise);
  }
};

/**
 * Processes a promise's resolution or rejection so that its value can be read
 * synchronously.  This enables using arbitrary matchers on the promise value:
 * <pre>
 *   var promise = instance.someAsyncOp();
 *   expect(promise).toHaveBeenResolved();
 *   expect(promiseUtils.getPromiseResult(promise).value).toBeLessThan(3);
 * </pre>
 * @param {!angular.$q.Promise} promise The promise to process.
 * @return {promiseUtils.PromiseResult} A PromiseResult for the
 *     promise.
 */
promiseUtils.getPromiseResult = function(promise) {
  promiseUtils.attachToPromiseOnce_(promise);
  inject(function($rootScope) { $rootScope.$apply(); });
  return promise[promiseUtils.PROMISE_RESULT_KEY_];
};

/**
 * Constructs Jasmine matcher message function for promise-related matchers
 * with given expected promise state.
 * @param {!promiseUtils.PromiseState} expected
 *     Expected promise state.
 * @param {!promiseUtils.PromiseState} actual Actual promise state.
 * @return {function():Array.<string>}
 * @private
 */
promiseUtils.stateMatcherMessage_ = function(expected, actual) {
  return function() {
    var maybeNot = this.isNot ? 'not ' : '';
    return 'Expected promise ' + maybeNot + 'to be ' +
        expected + ', but was ' + actual + '.';
  };
};

/**
 * Constructs Jasmine matcher message function for promise-related matchers
 * with given expected promise state and value.
 * @param {*} expected Expected promise value.
 * @param {*} actual Actual promise value.
 * @return {function():string}
 * @private
 */
promiseUtils.valueMatcherMessage_ = function(expected, actual) {
  return function() {
    var maybeNot = this.isNot ? 'not ' : '';
    return 'Expected promise value ' + maybeNot + 'to be [' +
        promiseUtils.dump_(expected) + '], but got [' +
        promiseUtils.dump_(actual) + '].';
  };
};

/**
 * Pretty-print an object for more useful expectation failure messages.
 * @param {*} data The data to pretty-print.
 * @private
 */
promiseUtils.dump_ = (window.angular && angular.mock.dump) || jasmine.pp || function(s) { return s; }

/**
 * Template for matcher that checks to see if the actual, a $q promise, was
 * resolved or rejected.
 * @param {promiseUtils.PromiseState} state Expected promise state.
 * @private
 */
promiseUtils.matchPromiseState_ = function(state) {
  return {
    compare: function(promise, expected) {
      var promiseResult = promiseUtils.getPromiseResult(promise);
      var message =
          promiseUtils.stateMatcherMessage_(state, promiseResult.state);
      var passed = promiseResult.state === state;
      return {
        pass: passed,
        message: message
      };
    }
  };
};

/**
 * Template for matcher that checks a $q promise's resolved value or rejection
 * reason.
 * @private
 */
promiseUtils.matchPromiseValue_ = function() {
  return {
    compare: function(promise, expected) {
      var promiseResult = promiseUtils.getPromiseResult(promise);
      return {
        pass: angular.equals(promiseResult.value, expected),
        message:  promiseUtils.valueMatcherMessage_(
          expected, promiseResult.value)
      };
    }
  };
};

/**
 * Map of Jasmine matchers to test $q promises. Pass this object to
 * {@code addMatchers} to register matchers in Jasmine.
 * @type {{
 *   toHaveBeenResolved:function(),
 *   toHaveBeenRejected:function(),
 *   toHaveBeenResolvedWith:function(*),
 *   toHaveBeenRejectedWith:function(*)
 * }}
 */
promiseUtils.jasmineMatchers = {
  /**
   * Matcher that checks to see if the actual, a $q promise, was resolved.
   * @this {jasmine.Matchers}
   * @return {boolean}
   */
  toHaveBeenResolved: function() {
    return promiseUtils.matchPromiseState_(promiseUtils.PromiseState.RESOLVED);
  },
  /**
   * Matcher that checks to see if the actual, a $q promise, was rejected.
   * @this {jasmine.Matchers}
   * @return {boolean}
   */
  toHaveBeenRejected: function() {
    return promiseUtils.matchPromiseState_(promiseUtils.PromiseState.REJECTED);
  },
  /**
   * Matcher that checks to see if the actual, a $q promise, is not yet resolved
   * or rejected.
   * @this {jasmine.Matchers}
   * @return {boolean}
   */
  toBePending: function() {
    return promiseUtils.matchPromiseState_(promiseUtils.PromiseState.PENDING);
  },
  /**
   * Matcher that checks to see if the actual, a $q promise, was resolved with a
   * specific value.
   * @this {jasmine.Matchers}
   * @param {*} value Expected value.
   * @return {boolean}
   */
  toHaveBeenResolvedWith: function() {
    return promiseUtils.matchPromiseState_(promiseUtils.PromiseState.RESOLVED) &&
        promiseUtils.matchPromiseValue_();
  },
  /**
   * Matcher that checks to see if the actual, a $q promise, was rejected with a
   * specific value.
   * @this {jasmine.Matchers}
   * @param {*} value Expected value.
   * @return {boolean}
   */
  toHaveBeenRejectedWith: function() {
    return promiseUtils.matchPromiseState_(
        promiseUtils.PromiseState.REJECTED) &&
        promiseUtils.matchPromiseValue_();
  }
};

/**
 * Creates a Jasmine spy function, which returns a $q promise. Also populates
 * the spy with methods to resolve and reject returned promise.
 * The spy can be used in a following way:
 * <pre>
 *   mockDependentService = {
 *     functionReturningPromise:
 *         promiseUtils.createSpyReturningPromise();
 *   };
 *   inject(function(serviceToTest) {
 *     serviceToTest.doStuffWithDependentService();
 *     // Test promise pending situation.
 *     mockDependentService.functionReturningPromise.resolveResult();
 *     // Test promise resolved situation.
 *   });
 * </pre>
 * @param {string} name A name to identify the spy.
 * @return {!jasmine.Spy}
 */
promiseUtils.createSpyReturningPromise = function(name) {
  var spy = jasmine.createSpy(name).and.callFake(function() {
    inject(function($q) {
      spy.deferred = $q.defer();
    });
    spy.deferreds_.push(spy.deferred);
    return spy.deferred.promise;
  });

  /**
   * The deferred instance for the last returned promise or null if the spy
   * function was never called.
   * Note that this only points to the last deferred regardless of how many have
   * been added or resolved.  Resolving or rejecting results does not change
   * this instance.
   * @type {?angular.$q.Deferred}
   */
  spy.deferred = null;

  /**
   * The deferred instance for the returned promises or empty list if the spy
   * function was never called.
   * @private {!Array.<!angular.$q.Deferred>}
   */
  spy.deferreds_ = [];

  /**
   * Resolves or rejects the last promise returned by the spy
   * function.
   * @param {string} resolveOrReject 'resolve' or 'reject' string.
   * @param {*} value Value to resolve promise.
   * @private
   */
  function resolveOrRejectResult_(resolveOrReject, value) {
    if (spy.deferreds_.length === 0) {
      throw new Error('Cannot ' + resolveOrReject +
          ' value returned by spy ' + spy.identity +
          ' because it has not been called.');
    }

    inject(function($rootScope) {
      // Promises are resolved and rejected asynchronously
      $rootScope.$apply(function() {
        var defer = spy.deferreds_.pop();
        defer[resolveOrReject](value);
      });
    });
  }

  /**
   * Resolves the last promise previously returned by spy the function.
   * If multiple promises were created then this resolves them in order from
   * last to first.
   * @param {*} value Value to resolve promise.
   */
  spy.resolveResult = function(value) {
    resolveOrRejectResult_('resolve', value);
  };

  /**
   * Rejects the last promise previously returned by spy the function.
   * If multiple promises were created then this rejects them in order from
   * last to first.
   * @param {*} value Value to reject promise.
   */
  spy.rejectResult = function(value) {
    resolveOrRejectResult_('reject', value);
  };

  return spy;
};
})()
