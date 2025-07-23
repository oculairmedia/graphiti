<p align="center" style="color: #444">
  <h1 align="center">Cosmograph</h1>
</p>

Cosmograph is a powerful and flexible visualization component built on top of the [@cosmograph/cosmos](https://github.com/cosmograph-org/cosmos#-cosmos) GPU-accelerated force graph layout algorithm and rendering engine.

## Features

- GPU-accelerated force graph layout algorithm and rendering engine
- Real-time simulation of network graphs with hundreds of thousands of nodes and edges on modern hardware
- Extensive configuration options
- Seamless integration with other components
- Can be use in a pure TypeScript or JavaScript app

## Installation

To install Cosmograph, run the following command:

```
npm install @cosmograph/cosmograph
```

## Usage

To use Cosmograph, import the `Cosmograph` class from `@cosmograph/cosmograph` and create a new instance of it with a div element and a configuration object. Then, set the data for the graph using the `setData` method.

```javascript
import { Cosmograph } from '@cosmograph/cosmograph'

const nodes = [
  { id: 0, color: 'red' },
  { id: 1, color: 'green' },
  { id: 2, color: 'blue' },
]

const links = [
  { source: 0, target: 1, color: 'blue' },
  { source: 1, target: 2, color: 'green' },
  { source: 2, target: 0, color:'red' },
]

const cosmographContainer = document.createElement('div')
const config = {
  simulation: {
    repulsion: 0.5,
  },
  renderLinks: true,
  linkColor: link => link.color,
  nodeColor: node => node.color,
  events: {
    onClick: node => {
      console.log('Clicked node: ', node)
    },
  },
  /* ... */
}

const cosmograph = new Cosmograph(canvas, config)
cosmograph.setData(nodes, links)
```

## Configuration

Cosmograph has an extensive set of configuration options that allow you to customize the appearance and behavior of the graph. For more information on configuration options, see the [documentation](https://cosmograph.app/docs/cosmograph/Cosmograph%20Library/Cosmograph/#passing-the-data-and-configuration).


## License

Cosmograph is licensed under the CC-BY-NC-4.0 license, or the Creative Commons Attribution-NonCommercial 4.0 International License.
