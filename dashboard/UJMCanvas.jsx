import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

const WIDTH = 860;
const HEIGHT = 420;

export default function UJMCanvas({ data, onNodeClick, livePointer }) {
  const containerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) {
      return undefined;
    }

    const svg = d3
      .select(containerRef.current)
      .append('svg')
      .attr('viewBox', `0 0 ${WIDTH} ${HEIGHT}`)
      .attr('class', 'w-full h-[420px] rounded-xl bg-gradient-to-br from-sand to-white');

    const nodeMap = new Map((data?.nodes || []).map((node) => [node.id, node]));

    const links = (data?.edges || [])
      .map((edge) => {
        const source = nodeMap.get(edge.source);
        const target = nodeMap.get(edge.target);
        if (!source || !target) {
          return null;
        }
        return { source, target };
      })
      .filter(Boolean);

    svg
      .append('g')
      .selectAll('path')
      .data(links)
      .join('path')
      .attr('d', (d) => `M ${d.source.x} ${d.source.y} Q ${(d.source.x + d.target.x) / 2} ${(d.source.y + d.target.y) / 2 - 30} ${d.target.x} ${d.target.y}`)
      .attr('fill', 'none')
      .attr('stroke', '#557a95')
      .attr('stroke-width', 2)
      .attr('stroke-opacity', 0.7);

    const nodes = svg
      .append('g')
      .selectAll('g')
      .data(data?.nodes || [])
      .join('g')
      .attr('transform', (d) => `translate(${d.x}, ${d.y})`)
      .style('cursor', 'pointer')
      .on('click', (_, d) => {
        if (typeof onNodeClick === 'function') {
          onNodeClick(d);
        }
      });

    nodes
      .append('circle')
      .attr('r', 24)
      .attr('fill', (d) => (d.anomaly ? '#d64933' : '#1f8a70'))
      .attr('stroke', '#ffffff')
      .attr('stroke-width', 3)
      .attr('opacity', 0.95);

    nodes
      .append('text')
      .text((d) => d.label)
      .attr('text-anchor', 'middle')
      .attr('dy', 44)
      .attr('font-size', 13)
      .attr('fill', '#13212e');

    if (livePointer && Number.isFinite(livePointer.xNorm) && Number.isFinite(livePointer.yNorm)) {
      const x = Math.max(0, Math.min(WIDTH, livePointer.xNorm * WIDTH));
      const y = Math.max(0, Math.min(HEIGHT, livePointer.yNorm * HEIGHT));

      const pointerGroup = svg.append('g');
      pointerGroup
        .append('circle')
        .attr('cx', x)
        .attr('cy', y)
        .attr('r', 12)
        .attr('fill', '#d64933')
        .attr('fill-opacity', 0.22)
        .attr('stroke', '#d64933')
        .attr('stroke-width', 2.5);

      pointerGroup
        .append('circle')
        .attr('cx', x)
        .attr('cy', y)
        .attr('r', 4)
        .attr('fill', '#d64933');

      pointerGroup
        .append('text')
        .attr('x', x + 10)
        .attr('y', y - 14)
        .attr('font-size', 12)
        .attr('fill', '#8a1f13')
        .text(`LIVE ${livePointer.deviceId || ''}`.trim());
    }

    return () => {
      svg.remove();
    };
  }, [data, onNodeClick, livePointer]);

  return <div ref={containerRef} className="w-full" />;
}
