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
