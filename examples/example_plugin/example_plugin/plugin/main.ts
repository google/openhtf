

import {
  Component,
  Input,
  OnInit,
} from 'angular2/core';

import {ExampleService} from './example_service';


/** The ExamplePlugin view component. **/
@Component({
  selector: 'example-plugin',
  templateUrl: 'plugin/example_plugin/example_plugin.html',
  providers: [ExampleService]
})
export class ExamplePlugin implements OnInit {
  //These inputs must be taken whether you use them or not
  @Input() currentMillis: number;
  @Input() stationInfo: any;
  @Input() currentMillisJob: number;
  @Input() tests: any[];
  private data: any;

  /**
   * Create a Example Plugin.
   */
  constructor(private exampleService: ExampleService) {
    this.data = {};
  }

  /**
   * Pull data from ExampleService
   */
  ngOnInit() {
    this.exampleService.requestData();
    this.data = this.exampleService.getData();
  }
  
}