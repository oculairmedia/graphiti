/**
 * @license
 * Copyright 2018 Google Inc.
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
 */
function e(e,r){if(e.closest)return e.closest(r);for(var n=e;n;){if(t(n,r))return n;n=n.parentElement}return null}function t(e,t){return(e.matches||e.webkitMatchesSelector||e.msMatchesSelector).call(e,t)}function r(e){var t=e;if(null!==t.offsetParent)return t.scrollWidth;var r=t.cloneNode(!0);r.style.setProperty("position","absolute"),r.style.setProperty("transform","translate(-9999px, -9999px)"),document.documentElement.appendChild(r);var n=r.scrollWidth;return document.documentElement.removeChild(r),n}export{e as closest,r as estimateScrollWidth,t as matches};
//# sourceMappingURL=ponyfill.js.map
