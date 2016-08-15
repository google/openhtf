// Copyright 2016 Google Inc.All Rights Reserved.

// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at

//     http://www.apache.org/licenses/LICENSE-2.0

// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

declare var jsonpatch; // Global provided by the fast-json-patch package.

import {Injectable} from 'angular2/core';
import {Http, Response} from 'angular2/http';
import 'rxjs/Rx';



@Injectable()
export class HistoryService {

  tests: any[];
  URL: string;
  station_id: string;

  constructor(private http: Http) {
    this.station_id = ''
    this.URL = ''
    this.tests = [];
  }

  requestTests() {
    this.http.get(this.URL)
      .map(response => response.json())
      .subscribe(
        data => this.updateTests(data),
        err => console.log('Error: ' + err)
      );
  }

  updateTests(data: any) {
    this.tests.push(data);
  }


  setStationId(id: string){
    this.station_id = id;
    this.URL = "/"+id+"/history";
  }

  getTests() {
    return this.tests;
  }

}