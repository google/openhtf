/**
 * @fileoverview A factory service which can poll to keep data up to date.
 *
 * It's fairly naive only scheduling a timeout after each poll finishes so it
 * does not try very hard to stay in the defined interval.
 */

var Backoff = require('backo');

/** @enum {number} */
var PollMode = module.exports.PollMode = {
  BACKGROUND: {min: 10000, max: 30000},
  INTERACTIVE: {min: 2000, max: 6000}
};

/**
 * @constructor
 * @param {angular.$timeout} $timeout
 */
function PollFactory($timeout, $log) {
  this.$timeout = $timeout;
  this.$log = $log;
}
module.exports.PollFactory = PollFactory;

/**
 * Creates a poll service which polls the method.
 * @param {function():angular.Promise} method
 * @param {string=} opt_name
 * @return {PollService}
 */
PollFactory.prototype.create = function(method, opt_name) {
  return new PollService(this.$timeout, this.$log, method, opt_name);
};

/**
 * @param {angular.$timeout} $timeout
 * @param {angular.$log} $log
 * @param {function():angular.Promise} method
 * @param {string=} opt_name
 * @constructor
 */
function PollService($timeout, $log, method, opt_name) {
  this.$timeout = $timeout;
  this.$log = $log;
  this.method = method;
  this.name = opt_name || method.name || "poller";

  this.timeoutPromise = null;
  this.setPollMode(PollMode.BACKGROUND);
}

/**
 * Sets the polling mode, takes affect the next poll.
 * @param {PollMode} pollMode
 */
PollService.prototype.setPollMode = function(pollMode) {
  this.backoff = new Backoff(pollMode);
  // We force a poll right now
  this.stop();
  this.pollNow().then(this.schedulePoll.bind(this));
};

/** Stops the poller and cancels any outstanding poll. */
PollService.prototype.stop = function() {
  if (this.timeoutPromise !== null) {
    this.$log.debug('Halting polling of ' + this.name);
    this.$timeout.cancel(this.timeoutPromise);
    this.timeoutPromise = null;
  }
};

/**
 * Schedules polling to occur again.
 */
PollService.prototype.schedulePoll = function() {
  if (this.timeoutPromise !== null) {
    return this.timeoutPromise;
  }

  var duration = this.backoff.duration();
  this.$log.debug('Scheduling ' + this.name + ' for ' + duration + 'ms');
  this.timeoutPromise = this.$timeout(function() {
    this.pollNow().then(this.onPollSuccess_.bind(this),
                        this.onPollFailure_.bind(this));
  }.bind(this), duration);
  return this.timeoutPromise;
};

/** @return {boolean} True if we're polling. */
PollService.prototype.isPolling = function() {
  return this.timeoutPromise !== null;
};

/**
 * Polls the function now.
 */
PollService.prototype.pollNow = function() {
  this.$log.debug('Polling now for ' + this.name);
  return this.method();
};

/**
 * Handles polling successfull
 * @private
 */
PollService.prototype.onPollSuccess_ = function() {
  this.backoff.reset();
  this.timeoutPromise = null;
  this.schedulePoll();
};

/**
 * Handles a polling failure
 * @private
 */
PollService.prototype.onPollFailure_ = function(err) {
  this.$log.warn('Polling failed', err);
  this.timeoutPromise = null;
  this.schedulePoll();
};
