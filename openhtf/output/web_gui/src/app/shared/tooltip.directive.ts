/**
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { Directive, ElementRef, HostListener, Input, OnInit } from '@angular/core';

@Directive({
  selector: '[htfTooltip]',
})
export class TooltipDirective implements OnInit {
  @Input('htfTooltip') text: string;

  private tooltipElement: HTMLDivElement;

  constructor(private ref: ElementRef) {}

  ngOnInit() {
    if (this.text.length === 0) {
      return;
    }
    this.tooltipElement = document.createElement('div');
    this.tooltipElement.innerHTML = this.text;
    this.tooltipElement.classList.add('ng-tooltip');
    const element = this.ref.nativeElement;
    element.classList.add('ng-tooltip-host');
    element.insertBefore(this.tooltipElement, element.firstChild);
  }

  @HostListener('mouseenter')
  onMouseEnter() {
    if (this.text.length > 0) {
      this.tooltipElement.classList.add('ng-tooltip--is-visible');
    }
  }

  @HostListener('mouseleave')
  onMouseLeave() {
    if (this.text.length > 0) {
      this.tooltipElement.classList.remove('ng-tooltip--is-visible');
    }
  }
}
