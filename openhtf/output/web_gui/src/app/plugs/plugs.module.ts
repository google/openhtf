/**
 * Feature module for plugs.
 *
 * See https://angular.io/docs/ts/latest/guide/ngmodule.html for more info
 * about modules in Angular.
 */

import { CommonModule } from '@angular/common';
import { NgModule } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpModule } from '@angular/http';

import { SharedModule } from '../shared/shared.module';

import { UserInputPlugComponent } from './user-input-plug.component';

@NgModule({
  imports: [
    CommonModule,
    FormsModule,
    HttpModule,
    SharedModule,
  ],
  declarations: [
    UserInputPlugComponent,
  ],
  providers: [],
  exports: [
    CommonModule,
    HttpModule,
    UserInputPlugComponent,
  ],
})
export class PlugsModule {
}
