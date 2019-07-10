import { Directive, ElementRef, Input, OnChanges } from '@angular/core';

@Directive({
  selector: '[htfFocus]',
})
export class FocusDirective implements OnChanges {
  @Input('htfFocus') focusOn: boolean;

  constructor(private ref: ElementRef) {}

  ngOnChanges() {
    if (this.focusOn) {
      this.ref.nativeElement.focus();
    }
  }
}
