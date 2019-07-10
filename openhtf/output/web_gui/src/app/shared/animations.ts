import { animate, state, style, transition } from '@angular/animations';

export const washIn = [
  state('in', style({
          'background': 'rgba(0, 119, 255, 0.0)',
        })),
  transition(
      'void => in',
      [
        style({
          'background': 'rgba(0, 119, 255, 0.1)',
        }),
        animate(1000),
      ]),
];

export function washAndExpandIn(maxHeight) {
  return [
    state('in', style({
            'background': 'rgba(0, 119, 255, 0.0)',
            'max-height': `${maxHeight}px`,
          })),
    transition(
        'void => in',
        [
          style({
            'background': 'rgba(0, 119, 255, 0.2)',
            'max-height': '0',
          }),
          animate(500),
        ]),
  ];
}
