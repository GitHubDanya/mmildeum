<script lang="ts">
    import {
        Chart,
        LineController,
        LineElement,
        PointElement,
        LinearScale,
        CategoryScale,
        Filler,
        Tooltip
    } from 'chart.js';
    import type { SparkChartConfig } from './types';
    import { HOURS_LABELS } from './telemetry';

    Chart.register(
        LineController,
        LineElement,
        PointElement,
        LinearScale,
        CategoryScale,
        Filler,
        Tooltip
    );

    export let title: string;
    export let data: number[];
    export let color = '#eaeaea';
    export let unit = '';
    export let min = 0;
    export let max = 100;
    export let stepped = false;
    export let summaryText = '';

    function hexToRgba(hex: string, alpha: number): string {
        const clean = hex.replace('#', '');
        const bigint = parseInt(clean, 16);
        const r = (bigint >> 16) & 255;
        const g = (bigint >> 8) & 255;
        const b = bigint & 255;
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    function minimalChart(node: HTMLCanvasElement, config: SparkChartConfig) {
        const buildDataset = (cfg: SparkChartConfig) => ({
            data: cfg.data,
            borderColor: cfg.color,
            borderWidth: 1.75,
            pointRadius: 0,
            pointHoverRadius: 3.5,
            pointHoverBackgroundColor: cfg.color,
            pointHoverBorderColor: '#070707',
            pointHoverBorderWidth: 1.5,
            tension: cfg.stepped ? 0 : 0.35,
            stepped: cfg.stepped ? ('middle' as const) : false,
            fill: true,
            backgroundColor: (context: any) => {
                const { ctx, chartArea } = context.chart;
                if (!chartArea) return 'transparent';
                const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                gradient.addColorStop(0, hexToRgba(cfg.color, 0.22));
                gradient.addColorStop(1, hexToRgba(cfg.color, 0.0));
                return gradient;
            }
        });

        const chart = new Chart(node, {
            type: 'line',
            data: {
                labels: HOURS_LABELS,
                datasets: [buildDataset(config)]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 250 },
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        enabled: true,
                        backgroundColor: '#0d0d0d',
                        titleColor: 'rgba(234, 234, 234, 0.65)',
                        bodyColor: '#ffffff',
                        borderColor: 'rgba(234, 234, 234, 0.2)',
                        borderWidth: 1,
                        padding: 8,
                        displayColors: false,
                        titleFont: { family: 'Rubik, sans-serif', size: 10, weight: 400 },
                        bodyFont: { family: 'Rubik, sans-serif', size: 12, weight: 600 },
                        callbacks: {
                            title: (items) => `${items[0]?.label ?? ''} UTC`,
                            label: (item) => `${Number(item.raw).toFixed(1)}${config.unit}`
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        border: { display: false },
                        ticks: {
                            color: 'rgba(234, 234, 234, 0.45)',
                            font: { family: 'Rubik, sans-serif', size: 9 },
                            maxRotation: 0,
                            autoSkip: false,
                            callback: (_val, index) =>
                                index % 6 === 0 || index === 23 ? HOURS_LABELS[index] : ''
                        }
                    },
                    y: {
                        min: config.min,
                        max: config.max,
                        border: { display: false },
                        grid: { color: 'rgba(234, 234, 234, 0.07)' },
                        ticks: {
                            color: 'rgba(234, 234, 234, 0.45)',
                            font: { family: 'Rubik, sans-serif', size: 9 },
                            maxTicksLimit: 3,
                            callback: (val) => `${val}${config.unit}`
                        }
                    }
                }
            }
        });

        return {
            update(newConfig: SparkChartConfig) {
                chart.data.datasets[0] = buildDataset(newConfig) as any;
                if (chart.options.scales?.y) {
                    chart.options.scales.y.min = newConfig.min;
                    chart.options.scales.y.max = newConfig.max;
                }
                chart.update();
            },
            destroy() {
                chart.destroy();
            }
        };
    }
</script>

<div class="graph-card">
    <div class="graph-meta">
        <span class="graph-title">{title}</span>
        {#if summaryText}
            <span class="graph-latest" style="color: {color};">{summaryText}</span>
        {/if}
    </div>
    <div class="canvas-wrap">
        <canvas use:minimalChart={{ data, color, unit, min, max, stepped }}></canvas>
    </div>
</div>

<style>
    .graph-card {
        background-color: rgba(7, 7, 7, 0.55);
        border: 1px solid rgba(234, 234, 234, 0.1);
        border-radius: 8px;
        padding: 0.5rem 0.65rem 0.4rem;
        display: flex;
        flex-direction: column;
        gap: 0.35rem;
    }

    .graph-meta {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 0.4rem;
    }

    .graph-title {
        font-size: 0.75rem;
        color: rgba(234, 234, 234, 0.9);
    }

    .graph-latest {
        font-size: 0.7rem;
        font-weight: 500;
        opacity: 0.85;
    }

    .canvas-wrap {
        position: relative;
        width: 100%;
        height: 82px;
    }
</style>