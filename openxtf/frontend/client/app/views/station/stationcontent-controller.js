/**
 * @fileoverview A controller for the station content.
 */

var proto = require('openxtf-proto').openxtf;

/**
 * @param {angular.Scope} $scope
 * @param {StationData} stationData
 * @param {number} cellNumber
 * @constructor
 */
function ContentController($scope, stationData, cellNumber) {
  this.stationData = stationData;
  this.cellNumber = cellNumber;
  this.parameters = null;

  var empty_params = [];
  $scope.$watch(function() {
    if (!this.hasTestRun()) {
      return empty_params;
    }
    return this.cell.test_parameters;
  }.bind(this), this.handleTestParametersChanged.bind(this));
}
module.exports = ContentController;

/** @return {boolean} True if there's a testrun for this cell. */
ContentController.prototype.hasTestRun = function() {
  return !!this.cell;
};

/** @return {number} The test run duration in ms */
ContentController.prototype.getTestDuration = function() {
  return this.cell.end_time_millis - this.cell.start_time_millis;
};

/**
 * @param {TestStatus=} opt_status
 * @return {boolean} True if this test run is in a finished state.
 */
ContentController.prototype.isFinished = function() {
  return [
    proto.Status.PASS,
    proto.Status.FAIL,
    proto.Status.ERROR,
    proto.Status.TIMEOUT,
    proto.Status.ABORTED
  ].indexOf(this.cell.test_status) != -1;
};

/** @return {Array.<TestRunLogMessage>} The reversed list of logs. */
ContentController.prototype.getTestLogs = function() {
  var logs = this.cell.test_logs.slice(0);
  logs.reverse();
  return logs;
};

ContentController.prototype.handleTestParametersChanged = function(
    newParameters) {
  var important = [], passed = [], failed = [], unset = [];
  newParameters.forEach(function(param) {
    var list = unset;
    if (param.important) {
      list = important;
    } else if (param.status == proto.Status.PASS) {
      list = passed;
    } else if (param.status == proto.Status.FAIL) {
      list = failed;
    }
    list.push(param);
  });
  var parameters = [];
  if (important.length) {
    parameters.push(new ParameterData(
        'Important Parameters', important, 'station-paramlist-important'));
  }
  if (failed.length) {
    parameters.push(new ParameterData('Failed Parameters', failed,
          'station-paramlist-failed'));
  }
  if (unset.length) {
    parameters.push(new ParameterData('Unset Parameters', unset,
          'station-paramlist-unset'));
  }
  if (passed.length) {
    parameters.push(new ParameterData('Passing Parameters', passed,
          'station-paramlist-passed'));
  }
  this.parameters = parameters;
};

/**
 * @param {string} name
 * @param {Array.<TestParameter>} values
 * @struct
 * @constructor
 */
function ParameterData(name, values, className) {
  this.name = name + ' (' + values.length + ')';
  this.className = className;
  this.values = values;
}

// We setup a property to make it easier to get the data from the view.
Object.defineProperty(ContentController.prototype, 'cell', {
  get: function() {
    return this.stationData.getData().cells[this.cellNumber - 1].test_run;
  }
});
