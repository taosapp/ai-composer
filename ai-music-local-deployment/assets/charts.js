(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  /* ---------- Chart 1: VRAM requirements ---------- */
  var vramEl = document.getElementById('chart-vram');
  if (vramEl && window.echarts) {
    var chart1 = echarts.init(vramEl, null, { renderer: 'svg' });

    var models = [
      'Stable Audio 3 Medium',
      'ACE-Step 1.5 2B',
      'Stable Audio Open 1.0',
      'ACE-Step v1 3.5B',
      'ACE-Step 1.5 XL 4B',
      'MusicGen large',
      'YuE2 3B',
      'YuE v1'
    ];
    var minData = [7, 4, 8, 8, 12, 16, 24, 24];
    var recData = [8, 8, 12, 16, 20, 24, 24, 80];

    chart1.setOption({
      animation: false,
      grid: { left: 150, right: 62, top: 44, bottom: 34 },
      legend: {
        top: 4,
        right: 4,
        itemWidth: 12,
        itemHeight: 8,
        textStyle: { color: muted, fontSize: 11 }
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        appendToBody: true,
        backgroundColor: bg2,
        borderColor: rule,
        textStyle: { color: ink, fontSize: 12 },
        formatter: function (params) {
          var name = params[0].name;
          var lines = '<b>' + name + '</b>';
          params.forEach(function (p) {
            var unit = p.seriesName === '推荐配置' && p.value >= 80 ? ' GB（整曲推荐）' : ' GB';
            lines += '<br/>' + p.marker + p.seriesName + '：' + p.value + unit;
          });
          return lines;
        }
      },
      xAxis: {
        type: 'value',
        name: '显存 (GB)',
        nameTextStyle: { color: muted, fontSize: 11, padding: [0, 0, 0, 8] },
        axisLabel: { color: muted, fontSize: 11 },
        axisLine: { lineStyle: { color: rule } },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } },
        max: 90
      },
      yAxis: {
        type: 'category',
        data: models,
        axisLabel: { color: ink, fontSize: 11.5 },
        axisLine: { lineStyle: { color: rule } },
        axisTick: { show: false }
      },
      series: [
        {
          name: '最低可运行',
          type: 'bar',
          data: minData,
          barWidth: 11,
          barGap: '25%',
          itemStyle: { color: accent + 'AA', borderRadius: [0, 2, 2, 0] },
          label: { show: false }
        },
        {
          name: '推荐配置',
          type: 'bar',
          data: recData,
          barWidth: 11,
          itemStyle: { color: accent2, borderRadius: [0, 2, 2, 0] },
          label: {
            show: true,
            position: 'right',
            color: muted,
            fontSize: 10.5,
            formatter: function (p) { return p.value + 'G'; }
          }
        }
      ]
    });

    window.addEventListener('resize', function () { chart1.resize(); });
  }

  /* ---------- Chart 2: quality vs generation time ---------- */
  var qualityEl = document.getElementById('chart-quality');
  if (qualityEl && window.echarts) {
    var chart2 = echarts.init(qualityEl, null, { renderer: 'svg' });

    var points = [
      { name: 'ACE-Step 1.5 2B', value: [10, 6.0118], note: '3090 整曲 &lt;10 秒' },
      { name: 'YuE2 3B', value: [71, 6.7316], note: '4090，3.6 分钟曲；best-of-8 达 6.9632' },
      { name: 'YuE v1', value: [2880, 4.9165], note: '按 6 分钟 / 30 秒音频推算的整曲耗时' }
    ];

    chart2.setOption({
      animation: false,
      grid: { left: 66, right: 40, top: 42, bottom: 56 },
      tooltip: {
        trigger: 'item',
        appendToBody: true,
        backgroundColor: bg2,
        borderColor: rule,
        textStyle: { color: ink, fontSize: 12 },
        formatter: function (p) {
          var d = p.data;
          return '<b>' + d.name + '</b><br/>SongBench Avg：' + d.value[1] +
            '<br/>整曲耗时：' + d.value[0] + ' 秒<br/><span style="color:' + muted + '">' + d.note + '</span>';
        }
      },
      xAxis: {
        type: 'log',
        name: '3–4 分钟整曲生成耗时（秒，对数轴）',
        nameLocation: 'middle',
        nameGap: 34,
        nameTextStyle: { color: muted, fontSize: 11 },
        min: 5,
        max: 4000,
        axisLabel: {
          color: muted,
          fontSize: 11,
          formatter: function (v) {
            if (v === 10) return '10s';
            if (v === 100) return '100s';
            if (v === 1000) return '1000s';
            return '';
          }
        },
        axisLine: { lineStyle: { color: rule } },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } }
      },
      yAxis: {
        type: 'value',
        name: 'SongBench Avg（满分 10）',
        nameTextStyle: { color: muted, fontSize: 11, align: 'left' },
        min: 4,
        max: 7.4,
        axisLabel: { color: muted, fontSize: 11 },
        axisLine: { lineStyle: { color: rule } },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } }
      },
      series: [
        {
          type: 'scatter',
          data: points,
          symbolSize: 16,
          itemStyle: {
            color: accent,
            borderColor: accent2,
            borderWidth: 1.5
          },
          label: {
            show: true,
            position: 'right',
            distance: 8,
            color: ink,
            fontSize: 11,
            formatter: function (p) { return p.data.name; }
          },
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { color: accent2, type: 'dashed', width: 1.5 },
            label: {
              position: 'insideEndTop',
              color: accent2,
              fontSize: 10,
              formatter: 'Suno v5 参考 6.87'
            },
            data: [{ yAxis: 6.8721 }]
          }
        }
      ]
    });

    window.addEventListener('resize', function () { chart2.resize(); });
  }
})();
