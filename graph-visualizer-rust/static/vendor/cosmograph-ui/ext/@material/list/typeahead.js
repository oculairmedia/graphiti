import{normalizeKey as e}from"../dom/keyboard.js";import{numbers as r}from"./constants.js";import{preventDefaultEvent as t}from"./events.js";
/**
 * @license
 * Copyright 2020 Google Inc.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */function n(){return{bufferClearTimeout:0,currentFirstChar:"",sortedIndexCursor:0,typeaheadBuffer:""}}function o(e,r){for(var t=new Map,n=0;n<e;n++){var o=r(n).trim();if(o){var d=o[0].toLowerCase();t.has(d)||t.set(d,[]),t.get(d).push({text:o.toLowerCase(),index:n})}}return t.forEach((function(e){e.sort((function(e,r){return e.index-r.index}))})),t}function d(e,t){var n,o=e.nextChar,d=e.focusItemAtIndex,s=e.sortedIndexByFirstChar,a=e.focusedItemIndex,f=e.skipFocus,i=e.isItemAtIndexDisabled;return clearTimeout(t.bufferClearTimeout),t.bufferClearTimeout=setTimeout((function(){u(t)}),r.TYPEAHEAD_BUFFER_CLEAR_TIMEOUT_MS),t.typeaheadBuffer=t.typeaheadBuffer+o,n=1===t.typeaheadBuffer.length?function(e,r,t,n){var o=n.typeaheadBuffer[0],d=e.get(o);if(!d)return-1;if(o===n.currentFirstChar&&d[n.sortedIndexCursor].index===r){n.sortedIndexCursor=(n.sortedIndexCursor+1)%d.length;var s=d[n.sortedIndexCursor].index;if(!t(s))return s}n.currentFirstChar=o;var u,a=-1;for(u=0;u<d.length;u++)if(!t(d[u].index)){a=u;break}for(;u<d.length;u++)if(d[u].index>r&&!t(d[u].index)){a=u;break}if(-1!==a)return n.sortedIndexCursor=a,d[n.sortedIndexCursor].index;return-1}(s,a,i,t):function(e,r,t){var n=t.typeaheadBuffer[0],o=e.get(n);if(!o)return-1;var d=o[t.sortedIndexCursor];if(0===d.text.lastIndexOf(t.typeaheadBuffer,0)&&!r(d.index))return d.index;var s=(t.sortedIndexCursor+1)%o.length,u=-1;for(;s!==t.sortedIndexCursor;){var a=o[s],f=0===a.text.lastIndexOf(t.typeaheadBuffer,0),i=!r(a.index);if(f&&i){u=s;break}s=(s+1)%o.length}if(-1!==u)return t.sortedIndexCursor=u,o[t.sortedIndexCursor].index;return-1}(s,i,t),-1===n||f||d(n),n}function s(e){return e.typeaheadBuffer.length>0}function u(e){e.typeaheadBuffer=""}function a(r,n){var o=r.event,u=r.isTargetListItem,a=r.focusedItemIndex,f=r.focusItemAtIndex,i=r.sortedIndexByFirstChar,x=r.isItemAtIndexDisabled,I="ArrowLeft"===e(o),h="ArrowUp"===e(o),c="ArrowRight"===e(o),C="ArrowDown"===e(o),m="Home"===e(o),p="End"===e(o),l="Enter"===e(o),y="Spacebar"===e(o);return o.altKey||o.ctrlKey||o.metaKey||I||h||c||C||m||p||l?-1:y||1!==o.key.length?y?(u&&t(o),u&&s(n)?d({focusItemAtIndex:f,focusedItemIndex:a,nextChar:" ",sortedIndexByFirstChar:i,skipFocus:!1,isItemAtIndexDisabled:x},n):-1):-1:(t(o),d({focusItemAtIndex:f,focusedItemIndex:a,nextChar:o.key.toLowerCase(),sortedIndexByFirstChar:i,skipFocus:!1,isItemAtIndexDisabled:x},n))}export{u as clearBuffer,a as handleKeydown,o as initSortedIndex,n as initState,s as isTypingInProgress,d as matchItem};
//# sourceMappingURL=typeahead.js.map
