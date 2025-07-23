import{__extends as t,__assign as e,__values as r}from"../../../../_virtual/_tslib.js";import{MDCFoundation as n}from"../../base/foundation.js";import{strings as a,cssClasses as i}from"./constants.js";
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
 */var o=["click","keydown"],s=function(n){function s(t){var r=n.call(this,e(e({},s.defaultAdapter),t))||this;return r.savedTabIndex=null,r.interactionHandler=function(t){r.handleInteraction(t)},r}return t(s,n),Object.defineProperty(s,"strings",{get:function(){return a},enumerable:!1,configurable:!0}),Object.defineProperty(s,"cssClasses",{get:function(){return i},enumerable:!1,configurable:!0}),Object.defineProperty(s,"defaultAdapter",{get:function(){return{getAttr:function(){return null},setAttr:function(){},removeAttr:function(){},setContent:function(){},registerInteractionHandler:function(){},deregisterInteractionHandler:function(){},notifyIconAction:function(){}}},enumerable:!1,configurable:!0}),s.prototype.init=function(){var t,e;this.savedTabIndex=this.adapter.getAttr("tabindex");try{for(var n=r(o),a=n.next();!a.done;a=n.next()){var i=a.value;this.adapter.registerInteractionHandler(i,this.interactionHandler)}}catch(e){t={error:e}}finally{try{a&&!a.done&&(e=n.return)&&e.call(n)}finally{if(t)throw t.error}}},s.prototype.destroy=function(){var t,e;try{for(var n=r(o),a=n.next();!a.done;a=n.next()){var i=a.value;this.adapter.deregisterInteractionHandler(i,this.interactionHandler)}}catch(e){t={error:e}}finally{try{a&&!a.done&&(e=n.return)&&e.call(n)}finally{if(t)throw t.error}}},s.prototype.setDisabled=function(t){this.savedTabIndex&&(t?(this.adapter.setAttr("tabindex","-1"),this.adapter.removeAttr("role")):(this.adapter.setAttr("tabindex",this.savedTabIndex),this.adapter.setAttr("role",a.ICON_ROLE)))},s.prototype.setAriaLabel=function(t){this.adapter.setAttr("aria-label",t)},s.prototype.setContent=function(t){this.adapter.setContent(t)},s.prototype.handleInteraction=function(t){var e="Enter"===t.key||13===t.keyCode;("click"===t.type||e)&&(t.preventDefault(),this.adapter.notifyIconAction())},s}(n);export{s as MDCTextFieldIconFoundation,s as default};
//# sourceMappingURL=foundation.js.map
