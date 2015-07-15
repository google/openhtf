// Copyright 2014 Google Inc. All Rights Reserved.
//
//  Licensed under the Apache License, Version 2.0 (the "License");
//  you may not use this file except in compliance with the License.
//  You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
//  Unless required by applicable law or agreed to in writing, software
//  distributed under the License is distributed on an "AS IS" BASIS,
//  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//  See the License for the specific language governing permissions and
//  limitations under the License.


/**
 * @fileoverview A controller for the station content.
 */

var proto = require('openhtf-proto').openhtf;

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
    var data = this.stationData.getData();
    if (data.cells.length > 0) {
      return this.stationData.getData().cells[this.cellNumber - 1].test_run;
    }
    else { return null; }
  }
});
