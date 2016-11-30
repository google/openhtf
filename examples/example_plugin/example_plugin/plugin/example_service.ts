
declare var jsonpatch; // Global provided by the fast-json-patch package.

import {Injectable} from 'angular2/core';
import {Http, Response} from 'angular2/http';
import 'rxjs/Rx';

@Injectable()
export class ExampleService {
  private data: any;
  private URL: string;

  /**
   * Create a ExampleService.
   */
  constructor(private http: Http) {
    this.data = {};
    this.URL = '/example/hello_world' //passing in hello_world as a parameter
  }

  /**
   * Sends HTTP request to Tornado server for data.
   */
  requestData() {
    this.http.get(this.URL)
      .map(response => response.json())
      .subscribe(
        data => this.updateData(data),
        err => console.log('Error: ' + err)
      );
  }


  /**
   * Updates current data with new information.
   */
  updateData(data: any[]) {
    let diff = jsonpatch.compare(this.data, data);
    jsonpatch.apply(this.data, diff);
  }

  /**
   * Returns data.
   */
  getData() {
    return this.data;
  }

}