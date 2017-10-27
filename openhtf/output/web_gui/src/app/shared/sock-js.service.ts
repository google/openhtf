/**
 * Provider for SockJS.
 *
 * This allows us to mock socket communication in unit tests.
 */

import { Injectable } from '@angular/core';

// Global provided by the sockjs_client library.
declare const SockJS: new (url: string) => SockJsObject;

export interface SockJsObject {
  close: () => void;
  onclose: {};
  onmessage: {};
  onopen: {};
}

export interface SockJsMessage { data: string; }

@Injectable()
export class SockJsService {
  sockJs = SockJS;
}
