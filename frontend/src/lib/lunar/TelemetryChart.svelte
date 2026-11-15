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
    export let labels: string[] = HOURS_LABELS;
    export let color = '#eaeaea';
    export let unit = '';
    export let min = 0;
    export let max = 100;
    export let stepped = false;
    export let summaryText = '';
    export let activeIndex: number | null = null;

    export let primaryLabel = 'Site A';
    export let compareData: number[] | undefined = undefined;
    export let compareColor = '#38bdf8';
    export let compareLabel = 'Site B';

    function hexToRgba(hex: string, alpha: number): string {
        const clean = hex.replace('#', '');
        const bigint = parseInt(clean, 16);
        const r = (bigint >> 16) & 255;
        const g = (bigint >> 8) & 255;
        const b = bigint & 255;
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    function buildSingleDataset(
        seriesData: number[],
        seriesColor: string,
        label: string,
        isStepped: boolean,
        fillAlpha: number
    ) {
        return {
            label,
            data: seriesData,
            borderColor: seriesColor,
            backgroundColor: (context: any) => {
                const { ctx, chartArea } = context.chart;
                if (!chartArea) return 'transparent';
                const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                gradient.addColorStop(0, hexToRgba(seriesColor, fillAlpha));
                gradient.addColorStop(1, hexToRgba(seriesColor, 0.0));
                return gradient;
            },
            borderWidth: 1.75,
            pointRadius: 0,
            pointHoverRadius: 3.5,
            pointHoverBackgroundColor: seriesColor,
            pointHoverBorderColor: '#070707',
            pointHoverBorderWidth: 1.5,
            tension: isStepped ? 0 : 0.35,
            stepped: isStepped ? ('middle' as const) : false,
            fill: true
        };
    }

    function buildDatasets(cfg: SparkChartConfig) {
        const isComparing = Array.isArray(cfg.compareData);
        const alpha = isComparing ? 0.08 : 0.22;

        const datasets = [
            buildSingleDataset(
                cfg.data,
                cfg.color,
                cfg.primaryLabel ?? 'Site A',
                Boolean(cfg.stepped),
                alpha
            )
        ];

        if (isComparing && cfg.compareData) {
            datasets.push(
                buildSingleDataset(
                    cfg.compareData,
                    cfg.compareColor ?? '#38bdf8',
                    cfg.compareLabel ?? 'Site B',
                    Boolean(cfg.stepped),
                    alpha
                )
            );
        }

        return datasets;
    }

    function minimalChart(node: HTMLCanvasElement, config: SparkChartConfig) {
        const getLabels = (cfg: SparkChartConfig) => cfg.labels ?? HOURS_LABELS;
        let currentCursorIndex = config.activeIndex ?? null;

        const cursorPlugin = {
            id: 'timelineCursor',
            afterDatasetsDraw(chartInstance: any) {
                if (currentCursorIndex === null || currentCursorIndex === undefined) return;
                const meta = chartInstance.getDatasetMeta(0);
                const point = meta?.data?.[currentCursorIndex];
                if (!point) return;

                const { ctx, chartArea } = chartInstance;
                ctx.save();
                ctx.beginPath();
                ctx.setLineDash([3, 3]);
                ctx.strokeStyle = 'rgba(255, 255, 255, 0.75)';
                ctx.lineWidth = 1.25;
                ctx.moveTo(point.x, chartArea.top);
                ctx.lineTo(point.x, chartArea.bottom);
                ctx.stroke();
                ctx.restore();
            }
        };

        const chart = new Chart(node, {
            type: 'line',
            data: {
                labels: getLabels(config),
                datasets: buildDatasets(config) as any
            },
            plugins: [cursorPlugin],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 200 },
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
                        displayColors: Array.isArray(config.compareData),
                        boxWidth: 8,
                        boxHeight: 8,
                        titleFont: { family: 'Rubik, sans-serif', size: 10, weight: 400 },
                        bodyFont: { family: 'Rubik, sans-serif', size: 11, weight: 600 },
                        callbacks: {
                            title: (items) => `${items[0]?.label ?? ''} UTC`,
                            label: (item) => {
                                const prefix = Array.isArray(config.compareData)
                                    ? `${item.dataset.label}: `
                                    : '';
                                return `${prefix}${Number(item.raw).toFixed(1)}${config.unit}`;
                            }
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
                            callback: function (_val, index) {
                                const activeLabels = (this.chart.data.labels as string[]) ?? [];
                                const total = activeLabels.length;
                                if (total <= 24) {
                                    return index % 6 === 0 || index === total - 1
                                        ? activeLabels[index]
                                        : '';
                                }
                                const step = Math.max(1, Math.floor((total - 1) / 4));
                                if (index % step === 0 || index === total - 1) {
                                    return (activeLabels[index] ?? '').replace(/\s+\d{2}:\d{2}$/, '');
                                }
                                return '';
                            }
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
                currentCursorIndex = newConfig.activeIndex ?? null;
                chart.data.labels = getLabels(newConfig);
                chart.data.datasets = buildDatasets(newConfig) as any;
                if (chart.options.plugins?.tooltip) {
                    chart.options.plugins.tooltip.displayColors = Array.isArray(
                        newConfig.compareData
                    );
                }
                if (chart.options.scales?.y) {
                    chart.options.scales.y.min = newConfig.min;
                    chart.options.scales.y.max = newConfig.max;
                }
                chart.update('none');
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
        {#if Array.isArray(compareData)}
            <div class="compare-legend">
                <span class="legend-item">
                    <i class="legend-dot" style="background: {color};"></i>
                    {primaryLabel}
                </span>
                <span class="legend-item">
                    <i class="legend-dot" style="background: {compareColor};"></i>
                    {compareLabel}
                </span>
            </div>
        {:else if summaryText}
            <span class="graph-latest" style="color: {color};">{summaryText}</span>
        {/if}
    </div>
    <div class="canvas-wrap">
        <canvas
                use:minimalChart={{
                data,
                labels,
                color,
                unit,
                min,
                max,
                stepped,
                activeIndex,
                primaryLabel,
                compareData,
                compareColor,
                compareLabel
            }}
        ></canvas>
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

    .compare-legend {
        display: flex;
        align-items: center;
        gap: 0.65rem;
        font-size: 0.68rem;
        color: rgba(234, 234, 234, 0.8);
    }

    .legend-item {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
    }

    .legend-dot {
        display: inline-block;
        width: 7px;
        height: 7px;
        border-radius: 999px;
    }

    .canvas-wrap {
        position: relative;
        width: 100%;
        height: 82px;
    }
</style>