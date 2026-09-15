module ChartHelper
  SOLVER_COLORS = {
    "solverforge" => "#d64a3a",
    "timefold" => "#3662c7",
    "ortools" => "#1b8a75",
    "pyvrp" => "#8b5cf6",
    "pyhygese" => "#d28b18",
    "rustvrp" => "#64748b",
    "vroom" => "#c026d3"
  }.freeze

  def solver_color(solver)
    SOLVER_COLORS.fetch(solver) do
      palette = SOLVER_COLORS.values
      palette[solver.to_s.bytes.sum % palette.length]
    end
  end

  def percent(value, precision: 0)
    return "n/a" if value.blank?

    number_to_percentage(value.to_f * 100, precision: precision)
  end

  def metric_number(value, precision: 2)
    return "n/a" if value.blank?

    number_with_precision(value.to_f, precision: precision, delimiter: ",")
  end

  def whole_number(value)
    number_with_delimiter(value.to_i)
  end

  def solver_label(solver)
    solver.to_s == "solverforge" ? "SolverForge" : solver.to_s
  end

  def timeline_chart(points, metric:, compact: false)
    series = points.group_by(&:solver)
    times = points.map { |point| timeline_time(point) }.uniq.sort
    values = points.filter_map { |point| metric_value(point, metric) }

    return tag.div("No historical points for this slice.", class: "empty-chart") if times.empty? || values.empty?

    width = 880.0
    height = 300.0
    padding_left = 54.0
    padding_right = 54.0
    padding_top = 24.0
    padding_bottom = 44.0
    plot_width = width - padding_left - padding_right
    plot_height = height - padding_top - padding_bottom
    min_value = [ values.min.to_f, 0.0 ].min
    max_value = values.max.to_f
    value_span = [ max_value - min_value, 1.0 ].max
    time_span = [ times.length - 1, 1 ].max

    x_for = lambda do |time|
      padding_left + (times.index(time).to_f / time_span * plot_width)
    end

    y_for = lambda do |value|
      padding_top + plot_height - ((value.to_f - min_value) / value_span * plot_height)
    end

    y_ticks = 4.times.map do |index|
      min_value + (value_span * index / 3.0)
    end

    tag.svg(
      viewBox: "0 0 #{width.to_i} #{height.to_i}",
      role: "img",
      class: compact ? "timeline-chart timeline-chart--compact" : "timeline-chart",
      aria: { label: metric.to_s.humanize }
    ) do
      safe_join([
        tag.g(class: "grid") do
          safe_join(y_ticks.map do |tick|
            y = y_for.call(tick)
            safe_join([
              tag.line(x1: padding_left, y1: y, x2: width - padding_right, y2: y),
              tag.text(metric_axis_label(tick, metric), x: 8, y: y + 4)
            ])
          end)
        end,
        safe_join(series.map do |solver, solver_points|
          point_lookup = solver_points.index_by { |point| timeline_time(point) }
          path_points = times.filter_map do |time|
            point = point_lookup[time]
            value = point && metric_value(point, metric)
            next unless value

            {
              x: x_for.call(time).round(2),
              y: y_for.call(value).round(2),
              label: "#{solver_label(solver)} · #{timeline_axis_label(time, times)} · #{metric_axis_label(value, metric)}"
            }
          end

          next if path_points.empty?

          color = solver_color(solver)
          safe_join([
            tag.polyline(points: path_points.map { |point| "#{point[:x]},#{point[:y]}" }.join(" "), fill: "none", stroke: color, "stroke-width": 3),
            safe_join(path_points.map do |point|
              tag.circle(cx: point[:x], cy: point[:y], r: 5, fill: color) do
                tag.title(point[:label])
              end
            end)
          ])
        end),
        tag.g(class: "axis-labels") do
          safe_join(axis_times(times).map do |time|
            tag.text(timeline_axis_label(time, times), x: x_for.call(time), y: height - 12, "text-anchor": "middle")
          end)
        end
      ])
    end
  end

  private

  def timeline_time(point)
    Time.zone.parse((point.try(:occurred_at) || point.day).to_s)
  end

  def axis_times(times)
    return times if times.size <= 4

    [ times.first, times[times.size / 3], times[(times.size * 2) / 3], times.last ].uniq
  end

  def timeline_axis_label(time, times)
    if times.map(&:to_date).uniq.one?
      time.strftime("%H:%M")
    else
      time.strftime("%b %-d %H:%M")
    end
  end

  def metric_value(point, metric)
    case metric
    when :feasibility
      return nil if point.result_count.to_i.zero?

      point.feasible_count.to_f / point.result_count.to_f
    when :quality_ratio
      point.avg_quality_ratio&.to_f
    when :cost
      point.avg_cost&.to_f
    else
      nil
    end
  end

  def metric_axis_label(value, metric)
    case metric
    when :feasibility
      percent(value, precision: 0)
    when :quality_ratio
      metric_number(value, precision: 2)
    when :cost
      metric_number(value, precision: 1)
    else
      metric_number(value, precision: 2)
    end
  end
end
