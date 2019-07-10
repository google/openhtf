/**
 * Tests for subscription.ts.
 */

import { fakeAsync, tick } from '@angular/core/testing';

import { SockJsMessage } from './sock-js.service';
import { MockSockJsInstance, MockSockJsService } from './sock-js.service.mock';

import { Subscription } from './subscription';

// Note: We use the fakeAsync zone in every test case to ensure that the test
// case fails if there is an unexpected timer (setTimeout) in the queue.
describe('subscription', () => {
  let mockSockJsInstance: MockSockJsInstance;
  let mockSockJsService: MockSockJsService;
  let subscription: Subscription;
  let sockJsSpy: jasmine.Spy;

  const connectSuccessfully = (instance: MockSockJsInstance = null) => {
    (instance || mockSockJsInstance).onopen();
  };

  const closeConnection = (instance: MockSockJsInstance = null) => {
    (instance || mockSockJsInstance).onclose();
  };

  const receiveMessage = (response: {}) => {
    mockSockJsInstance.onmessage({
      data: response,
    });
  };

  beforeEach(() => {
    // Set up SockJs mock.
    mockSockJsInstance = new MockSockJsInstance();
    mockSockJsService = new MockSockJsService();
    sockJsSpy =
        spyOn(mockSockJsService, 'sockJs').and.returnValue(mockSockJsInstance);

    // tslint:disable-next-line:no-any pass mock in place of real service
    subscription = new Subscription(mockSockJsService as any);
  });

  it('should begin in the unsubscribed state', fakeAsync(() => {
       expect(subscription.isSubscribing).toBe(false);
       expect(subscription.hasError).toBe(false);
     }));

  describe('after subscribing', () => {
    beforeEach(() => {
      subscription.subscribeToUrl('/mock/url');
    });

    it('should be in the subscribing state', fakeAsync(() => {
         expect(subscription.isSubscribing).toBe(true);
         expect(subscription.hasError).toBe(false);
       }));

    it('upon connecting, should be in the subscribed state', fakeAsync(() => {
         connectSuccessfully();
         expect(subscription.isSubscribing).toBe(false);
         expect(subscription.hasError).toBe(false);
       }));

    it('upon failing to connect, should be in the failed state',
       fakeAsync(() => {
         closeConnection();
         expect(subscription.isSubscribing).toBe(false);
         expect(subscription.hasError).toBe(true);
       }));

    it('upon connecting & closing, should be in failed state', fakeAsync(() => {
         connectSuccessfully();
         closeConnection();
         expect(subscription.isSubscribing).toBe(false);
         expect(subscription.hasError).toBe(true);
       }));

    it('after failing, should refresh', fakeAsync(() => {
         sockJsSpy.calls.reset();

         closeConnection();
         // Hitting refresh repeatedly should not cause duplicate requests.
         subscription.refresh();
         subscription.refresh();
         subscription.refresh();
         expect(subscription.isSubscribing).toBe(true);
         expect(subscription.hasError).toBe(false);

         connectSuccessfully();
         expect(subscription.isSubscribing).toBe(false);
         expect(subscription.hasError).toBe(false);
         expect(sockJsSpy.calls.count()).toBe(1);
         expect(sockJsSpy).toHaveBeenCalledWith('/mock/url');
       }));

    it('while subscribing, should do nothing on refresh', fakeAsync(() => {
         subscription.refresh();
         subscription.refresh();
         subscription.refresh();
         expect(sockJsSpy.calls.count()).toBe(1);
       }));

    it('while subscribing, should allow unsubscribe', fakeAsync(() => {
         subscription.unsubscribe();
         expect(subscription.isSubscribing).toBe(false);
         expect(subscription.hasError).toBe(false);
       }));

    it('should broadcast received messages', fakeAsync(() => {
         const responses1: Array<{}> = [];
         const responses2: Array<{}> = [];
         subscription.messages.subscribe((message: SockJsMessage) => {
           responses1.push(message.data);
         });
         subscription.messages.subscribe((message: SockJsMessage) => {
           responses2.push(message.data);
         });

         connectSuccessfully();
         receiveMessage({'message': 'mock-message-0'});
         receiveMessage({'message': 'mock-message-1'});
         expect(responses1.length).toEqual(2);
         expect(responses2.length).toEqual(2);
         expect(responses1[0]['message']).toEqual('mock-message-0');
         expect(responses1[1]['message']).toEqual('mock-message-1');
         expect(responses2[0]['message']).toEqual('mock-message-0');
         expect(responses2[1]['message']).toEqual('mock-message-1');
       }));

    it('should unsubscribe and resubscribe', fakeAsync(() => {
         connectSuccessfully();
         subscription.unsubscribe();
         subscription.subscribeToUrl('/mock/url');
         subscription.unsubscribe();
         subscription.subscribeToUrl('/mock/url');
         connectSuccessfully();
         expect(subscription.isSubscribing).toBe(false);
         expect(subscription.hasError).toBe(false);
         expect(sockJsSpy.calls.count()).toBe(3);
       }));
  });

  describe('after subscribing with auto-retry', () => {
    const retryMs = 100;
    const retryBackoff = 2.5;

    beforeEach(() => {
      subscription.subscribeToUrl('/mock/url', retryMs, retryBackoff);
    });

    it('upon failing to connect, should wait to reconnect', fakeAsync(() => {
         expect(subscription.retryTimeMs).toBe(null);

         closeConnection();
         expect(subscription.isSubscribing).toBe(false);
         expect(subscription.hasError).toBe(true);
         expect(subscription.retryTimeMs).not.toBe(null);

         tick(retryMs - 1);
         expect(subscription.isSubscribing).toBe(false);
         expect(subscription.hasError).toBe(true);

         tick(1);
         expect(subscription.isSubscribing).toBe(true);
         expect(subscription.hasError).toBe(false);
         expect(sockJsSpy.calls.count()).toBe(2);
       }));

    it('upon failing twice, should reconnect with backoff', fakeAsync(() => {
         closeConnection();
         const firstRetryTimeMs = subscription.retryTimeMs;
         tick(retryMs);
         closeConnection();
         tick(retryMs * retryBackoff - 1);
         expect(subscription.isSubscribing).toBe(false);
         expect(subscription.hasError).toBe(true);
         expect(subscription.retryTimeMs).not.toBe(null);
         expect(subscription.retryTimeMs).not.toEqual(firstRetryTimeMs);

         tick(1);
         expect(subscription.isSubscribing).toBe(true);
         expect(subscription.hasError).toBe(false);
         expect(sockJsSpy.calls.count()).toBe(3);
       }));

    it('after connecting, should reset backoff', fakeAsync(() => {
         closeConnection();
         tick(retryMs);
         closeConnection();
         tick(retryMs * retryBackoff);
         connectSuccessfully();
         closeConnection();
         tick(retryMs - 1);
         expect(subscription.isSubscribing).toBe(false);
         expect(subscription.hasError).toBe(true);

         tick(1);
         expect(subscription.isSubscribing).toBe(true);
         expect(subscription.hasError).toBe(false);
         expect(sockJsSpy.calls.count()).toBe(4);
       }));

    it('should retry immediately when asked to', fakeAsync(() => {
         closeConnection();
         subscription.retryNow();
         expect(subscription.isSubscribing).toBe(true);
         expect(subscription.hasError).toBe(false);
         expect(sockJsSpy.calls.count()).toBe(2);
       }));

    it('when waiting to auto-retry, should allow refresh', fakeAsync(() => {
         closeConnection();
         // Hitting refresh repeatedly should not cause duplicate requests.
         subscription.refresh();
         subscription.refresh();
         subscription.refresh();
         expect(subscription.isSubscribing).toBe(true);
         expect(subscription.hasError).toBe(false);
         expect(sockJsSpy.calls.count()).toBe(2);
       }));

    it('when waiting to auto-retry, should allow unsubscribe', fakeAsync(() => {
         closeConnection();
         subscription.unsubscribe();
         // With fakeAsync, this test will not pass if the timeout is not
         // canceled.
         expect(subscription.isSubscribing).toBe(false);
         expect(subscription.hasError).toBe(false);
       }));

    it('calling onclose many times should not cause problems', fakeAsync(() => {
         // Simulate a situation in which onclose is called by an old,
         // unsubscribed SockJS instance. When this happens we don't want extra
         // timeouts to be hanging around.

         // Simulate multiple SockJS instances.
         const mockSockJsInstance2 = new MockSockJsInstance();

         connectSuccessfully();

         sockJsSpy.and.returnValue(mockSockJsInstance2);
         subscription.refresh();
         connectSuccessfully(mockSockJsInstance2);
         closeConnection();
       }));
  });
});
