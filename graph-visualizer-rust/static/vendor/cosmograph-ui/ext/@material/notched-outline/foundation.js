import{__extends as t,__assign as e}from"../../../_virtual/_tslib.js";import{MDCFoundation as r}from"../base/foundation.js";import{strings as n,cssClasses as o,numbers as s}from"./constants.js";
/**
 * @license
 * Copyright 2017 Google Inc.
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
 */var a=function(r){function a(t){return r.call(this,e(e({},a.defaultAdapter),t))||this}return t(a,r),Object.defineProperty(a,"strings",{get:function(){return n},enumerable:!1,configurable:!0}),Object.defineProperty(a,"cssClasses",{get:function(){return o},enumerable:!1,configurable:!0}),Object.defineProperty(a,"numbers",{get:function(){return s},enumerable:!1,configurable:!0}),Object.defineProperty(a,"defaultAdapter",{get:function(){return{addClass:function(){},removeClass:function(){},setNotchWidthProperty:function(){},removeNotchWidthProperty:function(){}}},enumerable:!1,configurable:!0}),a.prototype.notch=function(t){var e=a.cssClasses.OUTLINE_NOTCHED;t>0&&(t+=s.NOTCH_ELEMENT_PADDING),this.adapter.setNotchWidthProperty(t),this.adapter.addClass(e)},a.prototype.closeNotch=function(){var t=a.cssClasses.OUTLINE_NOTCHED;this.adapter.removeClass(t),this.adapter.removeNotchWidthProperty()},a}(r);export{a as MDCNotchedOutlineFoundation,a as default};
//# sourceMappingURL=foundation.js.map
