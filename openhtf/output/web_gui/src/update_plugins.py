# Copyright 2016 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Adds/removes plugins."""


import argparse
import os
import sys
import shutil
import importlib

pre_html='''<!-- Template for the Station component; top level of the Station view. -->
<!-- ........................................................................... -->
<!-- THIS IS AUTO-GENERATED, IF YOU WANT TO EDIT GO TO update_plugins.py to edit -->
<!-- ........................................................................... -->
<div id="station">
  <station-header
    [stationInfo]="stationInfo"
    [plugins]="plugins">
  </station-header>
  <div class="currentTab" id="current">
    <div *ngIf="tests.length == 0" class="big-message">
      No tests available for display.
    </div>
    <div *ngFor="let test of tests">
      <div class="test">
        <test-header
          [dutID]="test.test_record?.dut_id"
          [startTime]="test.test_record?.start_time_millis"
          [endTime]="test.test_record?.end_time_millis"
          [currentMillis]="currentMillis"
          [status]="test.test_record?.outcome
                    || test.status || 'OFFLINE'">
        </test-header>
        <div class="test-content">
          <phase-listing id="phases" [state]="test"
                                     [currentMillis]="currentMillis">
          </phase-listing>
          <logs id="logs" [log_records]="test.test_record?.log_records">
          </logs>
          <metadata id="metadata" [metadata]="test.test_record.metadata">
          </metadata>
        </div>
      </div>
    </div>
  </div>
'''
post_html='''</div>'''

pre_ts="""// Copyright 2016 Google Inc.All Rights Reserved.

// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at

//     http://www.apache.org/licenses/LICENSE-2.0

// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/////////////////////////////////////////////////////////////////////////
//AUTOMATICALLY GENERATED - IF YOU WANT TO EDIT GO TO update_plugins.py//
/////////////////////////////////////////////////////////////////////////

declare var $;  // Global provided by the jquery package.

import {Component,
        OnDestroy,
        OnInit,
        SimpleChange} from 'angular2/core';
import {RouteParams} from 'angular2/router';
import {RouterLink} from 'angular2/router';

import {Logs} from './station.logs';
import {StationHeader} from './station.header';
import {Metadata} from './station.metadata';
import {PhaseListing} from './station.phases';
import {StationService} from './station.service';
import {TestHeader} from './station.testheader';
import {Countdown, ObjectToArray} from './utils';
import 'file?name=/styles/station.css!./station.css';
import 'file?name=/templates/station.html!./station.html';
"""

post_ts="""

/** Station view component. **/
@Component({{
  selector: 'station',
  templateUrl: 'templates/station.html',
  styleUrls: ['styles/station.css'],
  pipes: [ObjectToArray],
  directives: [StationHeader, TestHeader, PhaseListing, Logs, Metadata, {plugin_classes}],
  providers: [StationService]
}})
export class Station implements OnDestroy, OnInit {{
  private stationInfo: any;
  private currentMillis: number;
  private currentMillisJob: number;
  private tests: any[];
  private plugins: any[];

  /**
   * Create a Station view component.
   */
  constructor(private routeParams: RouteParams,
              private stationService: StationService) {{
    this.currentMillis = setInterval(() => {{
      this.currentMillis = Date.now();
    }}, 250);
    //This line is automatically generated, can be very long
    this.plugins={plugin_configs};
  }}

  /**
   * Set up the view component on initialization.
   */
  public ngOnInit(): any{{
    //Setting function to make tabs in history view work correctly
    $('station-header ul.tabs').tabs({{'onShow': function(tab){{
      if (tab.selector == '#history-header'){{
        $('.history-nav').show();
      }} else if (tab.selector != '#testList' && tab.selector != '#starred'){{
        $('.history-nav').hide();
      }}
    }}}});
    this.stationService.setHostPort(this.routeParams.get('host'),
                                    this.routeParams.get('port'));
    this.stationService.subscribe();
    this.stationInfo = this.stationService.getStationInfo();
    this.tests = this.stationService.getTests();
  }}

  /**
   * Tear down the view component when navigating away.
   */
  public ngOnDestroy() {{
    this.stationService.unsubscribe();
    clearInterval(this.currentMillisJob);
  }}

}}
"""

def add_html(tag):
  '''Returns html for individual plugin content 

  Args: 
    tag: a string representing the tag the plugin uses - 
    this is also reused for the id used in the tabs. 

  Returns: 
    A docstring representing the html for one plugin content
  '''
  return '''  <div id="'''+tag+'''" style="display: none;">
    <'''+tag+'''
      [stationInfo]="stationInfo"
      [currentMillis]="currentMillis"
      [currentMillisJob]="currentMillisJob"
      [tests]="tests">
    </'''+tag+'''>
  </div>
  '''



def main():
  # Take all cmd line arguments (plugin names)
  parser = argparse.ArgumentParser()
  parser.add_argument('plugins', nargs = '*', help = 'plugins')
  plugins = parser.parse_args().plugins

  # Make sure update_plugins is in correct directory
  try:
    if os.getcwd().split('openhtf/openhtf/')[1] != 'output/web_gui/src':
      raise
  except:
    print("Error: update_plugins currently not in openhtf/openhtf/output/web_gui/src")
    return

  # Delete and reinstantiate existing plugin dir in dist
  config_list=[]
  if os.path.exists("./dist/plugin/"):
    shutil.rmtree("./dist/plugin/")
  os.mkdir("./dist/plugin/")

  # Import plugins and copy frontend folders into dist/plugin
  for name in plugins:
    try:
      plugin_module = importlib.import_module(name)
      config = plugin_module.configs
      config['name']=name

      plugin_dir = plugin_module.__file__
      plugin_path = os.path.abspath(os.path.join(os.path.dirname(plugin_dir), "plugin"))
      shutil.copytree(plugin_path, "./dist/plugin/"+name+"/")
      config_list.append(config)
    except Exception, e:
      print("Error: Unable to add "+name+" plugin: "+str(e))


  # Generate station.html  
  with open("./station.html", 'w') as new_file:
    new_file.write(pre_html)
    for config in config_list:
      new_file.write(add_html(config['tag']))
    new_file.write(post_html)
    new_file.flush()

  if os.path.exists("./app/station.html"):
    os.remove("./app/station.html")
  shutil.move("./station.html", "./app/")


  # Generate station.ts
  with open("./station.ts", 'w') as new_file:
    new_file.write(pre_ts)
    for config in config_list:
      new_file.write("import {"+config['class']+"} from '../dist/plugin/"+config['name']+"/main';\n")
    class_list = "".join(config['class']+"," for config in config_list)
    new_file.write(post_ts.format(plugin_classes = class_list, plugin_configs = str(config_list)))
    new_file.flush()

  if os.path.exists("./app/station.ts"):
    os.remove("./app/station.ts")
  shutil.move("./station.ts", "./app/")


if __name__ == '__main__':
  main()