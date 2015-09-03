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
 * @fileoverview A service which tracks starred stations.
 */

var STAR_STORAGE_KEY = 'openhtf.client.starred';

var FAKE_STORE = {setItem: function() {}, getItem: function() {}};

function getLocalStorage() {
  if (window.localStorage) {
    return window.localStorage;
  } else {
    return FAKE_STORE;
  }
}

/** @constructor */
function StarService($rootScope) {
  this.$rootScope = $rootScope;
  this.storage = getLocalStorage();
  var instorage = this.storage.getItem(STAR_STORAGE_KEY);
  try {
    this.starred = JSON.parse(instorage) || {};
  } catch (err) {
    this.starred = {};
  }
}
module.exports = StarService;

/**
 * Toggles the station.
 * @param {string} stationName
 */
StarService.prototype.toggleStarred = function(stationName) {
  if (stationName in this.starred) {
    delete this.starred[stationName];
  } else {
    this.starred[stationName] = true;
  }

  this.storage.setItem(STAR_STORAGE_KEY, JSON.stringify(this.starred));
};

/**
 * @param {string} stationName
 * @return {boolean} True if this station is starred.
 */
StarService.prototype.isStarred = function(stationName) {
  return !!this.starred[stationName];
};

/** @return {string} Returns the list of starred stations. */
StarService.prototype.getStarred = function() {
  return Object.keys(this.starred);
};
