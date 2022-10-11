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
 * Mock for use in unit tests of classes that depend on SockJsService.
 */

export class MockSockJsInstance {
  // The instance is configured by setting these callbacks on the object.
  onclose;
  onmessage;
  onopen;

  close() {}
}

export class MockSockJsService {
  sockJs(_url: string) {
    return new MockSockJsInstance();
  }
}
