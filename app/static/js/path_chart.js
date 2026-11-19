/* Pathology chart drawing, shared by the atomised results page and the results-
 * outside-range page (ADR-097). One test: its values over time, the laboratory's range
 * shaded, the limits dashed. Needs Chart.js and moment (+ chartjs-adapter-moment).
 *
 * PathChart.draw(canvas, data, testName, opts) → the Chart.
 *   data: {title, units, subtitle, data: [{x: 'YYYY-MM-DD', y, yLow?}],
 *          scale: {normalMin?, normalMax?, min?, max?, autoScale?, isIdealWeight?}}
 *   opts.highlightLast: mark the most recent point.
 */
(function () {
    'use strict';
    function draw(canvas, data, testName, opts) {
        opts = opts || {};
        const textColor  = '#212529';
        const mutedColor = '#6c757d';
        const gridColor  = 'rgba(0,0,0,0.08)';

        const colors = {
            mainLine:     'rgba(75, 192, 192, 1)',
            mainFill:     'rgba(75, 192, 192, 0.08)',
            abnormalHigh: 'rgba(220, 53, 69, 0.12)',
            abnormalLow:  'rgba(220, 53, 69, 0.12)',
            normalRange:  'rgba(40, 167, 69, 0.10)',
            lineMax:      'rgba(220, 53, 69, 0.6)',
            lineMin:      'rgba(255, 193, 7, 0.6)',
            lineWidth:    2,
            boundaryDash: [5, 5],
        };

        const parsedData = data.data.map(p => ({
            x: moment(p.x, 'YYYY-MM-DD').toDate(),
            y: p.y,
        }));

        let minDate, maxDate;
        if (parsedData.length > 1) {
            const dates = parsedData.map(p => p.x.getTime());
            minDate = new Date(Math.min(...dates));
            maxDate = new Date(Math.max(...dates));
        } else {
            minDate = moment(parsedData[0].x).subtract(1, 'months').toDate();
            maxDate = moment(parsedData[0].x).add(1, 'months').toDate();
        }

        let subtitleText = '';
        if (data.subtitle) {
            subtitleText = Array.isArray(data.subtitle) ? data.subtitle.join('\n') : data.subtitle;
        }

        const datasets = [];

        if (testName === 'Blood Pressure') {
            datasets.push({
                label: 'Systolic',
                data: parsedData.map(p => ({ x: p.x, y: p.y })),
                borderColor: colors.mainLine, backgroundColor: 'transparent',
                borderWidth: colors.lineWidth, fill: false, tension: 0.1,
                pointRadius: 3, pointHoverRadius: 5, order: 1,
            });
            datasets.push({
                label: 'Diastolic',
                data: data.data.map(p => ({ x: moment(p.x, 'YYYY-MM-DD').toDate(), y: p.yLow })),
                borderColor: '#36a2eb', backgroundColor: 'transparent',
                borderWidth: colors.lineWidth, fill: false, tension: 0.1,
                pointRadius: 3, pointHoverRadius: 5, order: 1,
            });
        } else {
            datasets.push({
                label: data.title,
                data: parsedData,
                borderColor: colors.mainLine, backgroundColor: colors.mainFill,
                borderWidth: colors.lineWidth, fill: false, tension: 0.1,
                pointRadius: 3, pointHoverRadius: 5, order: 1,
            });
        }

        const scaleConfig   = data.scale || {};
        const normalMin     = scaleConfig.normalMin;
        const normalMax     = scaleConfig.normalMax;
        const yMin          = scaleConfig.min;
        const yMax          = scaleConfig.max;
        const isIdealWeight = scaleConfig.isIdealWeight;

        if (normalMin !== undefined && normalMax !== undefined) {
            datasets.push({ label: 'Range',  data: parsedData.map(p => ({ x: p.x, y: normalMax })), borderColor: 'transparent', backgroundColor: colors.normalRange,  borderWidth: 0, fill: { value: normalMin },                                       pointRadius: 0, order: 15 });
            datasets.push({ label: 'Below range',  data: parsedData.map(p => ({ x: p.x, y: normalMin })), borderColor: 'transparent', backgroundColor: colors.abnormalLow,  borderWidth: 0, fill: 'start',                                                    pointRadius: 0, order: 10 });
            datasets.push({ label: 'Above range', data: parsedData.map(p => ({ x: p.x, y: yMax !== undefined ? yMax : normalMax * 1.5 })), borderColor: 'transparent', backgroundColor: colors.abnormalHigh, borderWidth: 0, fill: { value: normalMax },     pointRadius: 0, order: 11 });
            datasets.push({ label: isIdealWeight ? 'BMI 25' : 'Range max', data: parsedData.map(p => ({ x: p.x, y: normalMax })), borderColor: colors.lineMax, borderWidth: colors.lineWidth, borderDash: colors.boundaryDash, pointRadius: 0, fill: false, order: 2 });
            datasets.push({ label: 'Range min', data: parsedData.map(p => ({ x: p.x, y: normalMin })), borderColor: colors.lineMin, borderWidth: colors.lineWidth, borderDash: colors.boundaryDash, pointRadius: 0, fill: false, order: 3 });
        } else if (normalMax !== undefined) {
            datasets.push({ label: isIdealWeight ? 'BMI 20 to 25' : 'Range',     data: parsedData.map(p => ({ x: p.x, y: normalMax })), borderColor: 'transparent', backgroundColor: colors.normalRange,  borderWidth: 0, fill: 'start',                                               pointRadius: 0, order: 15 });
            datasets.push({ label: isIdealWeight ? 'Above BMI 25' : 'Above range',    data: parsedData.map(p => ({ x: p.x, y: yMax !== undefined ? yMax : normalMax * 1.5 })), borderColor: 'transparent', backgroundColor: colors.abnormalHigh, borderWidth: 0, fill: { value: normalMax }, pointRadius: 0, order: 10 });
            datasets.push({ label: isIdealWeight ? 'BMI 25'   : 'Range max',       data: parsedData.map(p => ({ x: p.x, y: normalMax })), borderColor: colors.lineMax, borderWidth: colors.lineWidth, borderDash: colors.boundaryDash, pointRadius: 0, fill: false, order: 2 });
        } else if (normalMin !== undefined) {
            datasets.push({ label: 'Range', data: parsedData.map(p => ({ x: p.x, y: yMax !== undefined ? yMax : normalMin * 2 })), borderColor: 'transparent', backgroundColor: colors.normalRange, borderWidth: 0, fill: { value: normalMin }, pointRadius: 0, order: 15 });
            datasets.push({ label: 'Below range', data: parsedData.map(p => ({ x: p.x, y: normalMin })), borderColor: 'transparent', backgroundColor: colors.abnormalLow, borderWidth: 0, fill: 'start', pointRadius: 0, order: 10 });
            datasets.push({ label: 'Range min', data: parsedData.map(p => ({ x: p.x, y: normalMin })), borderColor: colors.lineMin, borderWidth: colors.lineWidth, borderDash: colors.boundaryDash, pointRadius: 0, fill: false, order: 2 });
        }

        const yScaleConfig = {
            beginAtZero: false,
            title: { display: true, text: data.units || 'Value', color: textColor, font: { size: 14, weight: 'bold' } },
            ticks: { color: textColor, font: { size: 12 } },
            grid:  { color: gridColor },
        };
        if (!scaleConfig.autoScale) {
            if (scaleConfig.min !== undefined) yScaleConfig.min = scaleConfig.min;
            if (scaleConfig.max !== undefined) yScaleConfig.max = scaleConfig.max;
        }

        if (opts.highlightLast && datasets.length) {
            const n = datasets[0].data.length;
            datasets[0].pointRadius = datasets[0].data.map((_, i) => i === n - 1 ? 6 : 3);
            datasets[0].pointBackgroundColor = datasets[0].data.map((_, i) =>
                i === n - 1 ? 'rgba(220, 53, 69, 1)' : 'rgba(75, 192, 192, 1)');
        }

        return new Chart(canvas.getContext('2d'), {
            type: 'line',
            data: { datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        type: 'time',
                        time: { unit: 'month', tooltipFormat: 'YYYY-MM-DD', displayFormats: { month: 'MM/YYYY', year: 'YYYY' } },
                        title: { display: true, text: 'Performed Date', color: textColor, font: { size: 12, weight: 'bold' } },
                        ticks: { color: textColor },
                        min: minDate,
                        max: maxDate,
                        grid: { color: gridColor },
                    },
                    y: yScaleConfig,
                },
                plugins: {
                    title:    { display: false },
                    subtitle: {
                        display: !!subtitleText,
                        text:    subtitleText,
                        font:    { size: 12, style: 'italic', weight: 'normal' },
                        padding: { bottom: 10 },
                        color:   mutedColor,
                    },
                    tooltip: {
                        callbacks: {
                            title: ctx => moment(ctx[0].parsed.x).format('DD/MM/YYYY'),
                            label: ctx => {
                                if (testName === 'Blood Pressure')
                                    return `${ctx.dataset.label}: ${ctx.parsed.y} ${data.units || ''}`;
                                return `Value: ${ctx.parsed.y} ${data.units || ''}`;
                            },
                        },
                        backgroundColor: 'rgba(0,0,0,0.8)',
                        padding:         10,
                        cornerRadius:    4,
                    },
                    legend: { display: testName === 'Blood Pressure' },
                },
                interaction: { intersect: true, mode: 'nearest' },
            },
        });
    }

    window.PathChart = {draw};
})();
