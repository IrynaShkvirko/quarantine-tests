import { visit } from 'unist-util-visit';

/**
 * Turns ```mermaid code blocks into <Mermaid chart="..." /> so diagrams render
 * in both the user docs and the synced engineering docs, without changing the
 * Markdown that GitHub and the agents read.
 */
export function remarkMermaid() {
  return (tree) => {
    visit(tree, 'code', (node, index, parent) => {
      if (node.lang !== 'mermaid' || !parent || index === undefined) return;
      parent.children[index] = {
        type: 'mdxJsxFlowElement',
        name: 'Mermaid',
        attributes: [{ type: 'mdxJsxAttribute', name: 'chart', value: node.value }],
        children: [],
      };
    });
  };
}
