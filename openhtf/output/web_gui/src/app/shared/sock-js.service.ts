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
