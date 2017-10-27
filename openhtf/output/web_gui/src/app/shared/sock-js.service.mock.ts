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
