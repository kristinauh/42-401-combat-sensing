%% Load, clean, and forward-fill BLE data paired with reference measurements
clear; clc;
filename = 'data/integrated_KH.csv';
T = readtable(filename);

cols_wanted = {'time', 'activity_label', 'ble_hr', 'ble_spo2', 'ref_hr', 'ref_spo2'};
T = T(:, cols_wanted);

T.ble_hr_filled   = fillmissing(T.ble_hr,   'linear');
T.ble_spo2_filled = fillmissing(T.ble_spo2, 'linear');

has_ref = ~isnan(T.ref_hr) | ~isnan(T.ref_spo2);
T_paired = T(has_ref, :);

T_final = table( ...
    T_paired.time, ...
    T_paired.activity_label, ...
    T_paired.ble_hr_filled, ...
    T_paired.ref_hr, ...
    T_paired.ble_spo2_filled, ...
    T_paired.ref_spo2, ...
    'VariableNames', {'time','activity_label','ble_hr','ref_hr','ble_spo2','ref_spo2'});

still_nan = isnan(T_final.ble_hr) & isnan(T_final.ble_spo2);
T_final(still_nan, :) = [];

T_final(strcmp(T_final.activity_label, 'PPG_WARMUP'), :) = [];

disp(head(T_final, 5));
fprintf('Total paired rows: %d\n', height(T_final));

FS = 14;
LW = 1.5;
C_STILL  = [0.20 0.40 0.75];
C_MOVING = [0.85 0.25 0.25];

% Pretty labels for figures
pretty_map = containers.Map( ...
    {'BASELINE_STILL','RECOVERY_STILL','SIT_QUICK','WALK_SLOW','WALK_FAST', ...
     'RUN','JUMP_SINGLE','JUMP_REPEATED','FALL_FORWARD','FALL_BACKWARD','FALL_SIDE'}, ...
    {'Still','Still','Sit','Slow Walk','Fast Walk', ...
     'Run','Jump','Jumps','Fall Fwd','Fall Back','Fall Side'});
pretty = @(x) pretty_map(x);


%% HR scatter
ref = T_final.ref_hr;
ble = T_final.ble_hr;
labels = T_final.activity_label;

still_acts = {'BASELINE_STILL','RECOVERY_STILL'};
is_still = ismember(labels, still_acts);

mae_all    = mean(abs(ref - ble));
mae_still  = mean(abs(ref(is_still)  - ble(is_still)));
mae_moving = mean(abs(ref(~is_still) - ble(~is_still)));

figure('Color','w','Position',[100 100 560 500]);
scatter(ref(is_still),  ble(is_still),  55, 'o', 'MarkerFaceColor', C_STILL,  'MarkerEdgeColor','w'); hold on;
scatter(ref(~is_still), ble(~is_still), 55, 'o', 'MarkerFaceColor', C_MOVING, 'MarkerEdgeColor','w');

lims = [min([ref;ble])-5, max([ref;ble])+5];
plot(lims, lims, '--', 'Color',[0.5 0.5 0.5], 'LineWidth', 1.2);

xlabel('Reference HR (bpm)');
ylabel('Measured HR (bpm)');
legend({sprintf('Still (MAE = %.2f)', mae_still), ...
        sprintf('Moving (MAE = %.2f)', mae_moving)}, 'Location','best', 'Box','off');
axis equal; xlim(lims); ylim(lims); grid on;
style_ax(gca, FS);


%% SpO2 scatter
ref = T_final.ref_spo2;
ble = T_final.ble_spo2;
labels = T_final.activity_label;

is_still = ismember(labels, still_acts);

mae_all    = mean(abs(ref - ble));
mae_still  = mean(abs(ref(is_still)  - ble(is_still)));
mae_moving = mean(abs(ref(~is_still) - ble(~is_still)));

figure('Color','w','Position',[100 100 560 500]);
scatter(ref(is_still),  ble(is_still),  55, 'o', 'MarkerFaceColor', C_STILL,  'MarkerEdgeColor','w'); hold on;
scatter(ref(~is_still), ble(~is_still), 55, 'o', 'MarkerFaceColor', C_MOVING, 'MarkerEdgeColor','w');

lims = [min([ref;ble])-1, max([ref;ble])+1];
plot(lims, lims, '--', 'Color',[0.5 0.5 0.5], 'LineWidth', 1.2);

xlabel('Reference SpO_{2} (%)');
ylabel('Measured SpO_{2} (%)');
legend({sprintf('Still (MAE = %.2f)', mae_still), ...
        sprintf('Moving (MAE = %.2f)', mae_moving)}, 'Location','best', 'Box','off');
axis equal; xlim(lims); ylim(lims); grid on;
style_ax(gca, FS);


%% Time series: ref vs measured HR and SpO2
t = T_final.time;
labels = T_final.activity_label;
change_idx = [1; find(~strcmp(labels(1:end-1), labels(2:end))) + 1];
change_times = t(change_idx);
change_labels = cellfun(pretty, labels(change_idx), 'UniformOutput', false);

figure('Color','w','Position',[100 100 1100 650]);

subplot(2,1,1);
plot(t, T_final.ref_hr, 'k-', 'LineWidth', LW); hold on;
plot(t, T_final.ble_hr, '-', 'Color', C_MOVING, 'LineWidth', LW);
for i = 1:numel(change_times)
    xline(change_times(i), 'Color', [0.75 0.75 0.75]);
end
ylabel('HR (bpm)');
legend({'Reference','Measured'}, 'Location','best', 'Box','off');
xticks(change_times); xticklabels(change_labels);
xtickangle(45);
grid on;
style_ax(gca, FS);

subplot(2,1,2);
plot(t, T_final.ref_spo2, 'k-', 'LineWidth', LW); hold on;
plot(t, T_final.ble_spo2, '-', 'Color', C_STILL, 'LineWidth', LW);
for i = 1:numel(change_times)
    xline(change_times(i), 'Color', [0.75 0.75 0.75]);
end
ylabel('SpO_{2} (%)');
legend({'Reference','Measured'}, 'Location','best', 'Box','off');
xticks(change_times); xticklabels(change_labels);
xtickangle(45);
grid on;
style_ax(gca, FS);

%% Per-activity time series grid
labels = T_final.activity_label;
unique_acts = unique(labels, 'stable');
n = numel(unique_acts);

n_cols = 4;
n_rows = ceil(n / n_cols);

figure('Color','w','Position', [100 100 1000 600]);
for i = 1:n
    mask = strcmp(labels, unique_acts{i});
    t_act   = T_final.time(mask);
    t_act   = t_act - min(t_act);  % reset to start at 0
    ref_act = T_final.ref_hr(mask);
    ble_act = T_final.ble_hr(mask);
    mae_act = mean(abs(ref_act - ble_act));

    subplot(n_rows, n_cols, i);
    plot(t_act, ref_act, 'k-', 'LineWidth', LW); hold on;
    plot(t_act, ble_act, '-', 'Color', C_MOVING, 'LineWidth', LW);
    title(sprintf('%s (MAE=%.1f)', pretty(unique_acts{i}), mae_act), ...
        'FontWeight', 'normal', 'FontSize', FS-2);
    xlabel('Time (s)');
    ylabel('HR (bpm)');
    grid on;
    style_ax(gca, FS-2);
end

ax_legend = subplot(n_rows, n_cols, n_rows * n_cols);
hold(ax_legend, 'on');
h1 = plot(ax_legend, NaN, NaN, 'k-', 'LineWidth', LW);
h2 = plot(ax_legend, NaN, NaN, '-', 'Color', C_MOVING, 'LineWidth', LW);
axis(ax_legend, 'off');
legend(ax_legend, [h1 h2], {'Reference','Measured'}, ...
    'Location', 'west', 'Box', 'off', 'FontSize', FS);


%% MAE summary
fprintf('HR   MAE: %.2f bpm\n', mean(abs(T_final.ref_hr - T_final.ble_hr)));
fprintf('SpO2 MAE: %.2f %%\n\n', mean(abs(T_final.ref_spo2 - T_final.ble_spo2)));

act_map = containers.Map( ...
    {'BASELINE_STILL','RECOVERY_STILL','SIT_QUICK','WALK_SLOW','WALK_FAST', ...
     'RUN','JUMP_SINGLE','JUMP_REPEATED','FALL_FORWARD','FALL_BACKWARD','FALL_SIDE'}, ...
    {'STILL','STILL','SIT','WALK','WALK','RUN','JUMP','JUMP','FALL','FALL','FALL'});

simple = cellfun(@(a) act_map(a), T_final.activity_label, 'UniformOutput', false);

cats = {'STILL','SIT','WALK','RUN','JUMP','FALL'};
fprintf('%-10s %8s %10s %12s\n', 'Activity', 'N', 'HR MAE', 'SpO2 MAE');
fprintf('%s\n', repmat('-', 1, 42));
for i = 1:numel(cats)
    m = strcmp(simple, cats{i});
    fprintf('%-10s %8d %10.2f %12.2f\n', cats{i}, sum(m), ...
        mean(abs(T_final.ref_hr(m)   - T_final.ble_hr(m))), ...
        mean(abs(T_final.ref_spo2(m) - T_final.ble_spo2(m))));
end


%% IMU preprocessing
T_imu = readtable(filename);
T_imu = T_imu(:, {'time', 'activity_label', 'imu_state'});

T_imu(strcmp(T_imu.activity_label, 'PPG_WARMUP'), :) = [];

still_acts = {'BASELINE_STILL','RECOVERY_STILL'};
keep = ~cellfun(@isempty, T_imu.imu_state) | ismember(T_imu.activity_label, still_acts);
T_imu = T_imu(keep, :);


%% Confusion matrix
act_map = containers.Map( ...
    {'BASELINE_STILL','RECOVERY_STILL','SIT_QUICK','WALK_SLOW','WALK_FAST', ...
     'RUN','JUMP_SINGLE','JUMP_REPEATED','FALL_FORWARD','FALL_BACKWARD','FALL_SIDE'}, ...
    {'STILL','STILL','SIT','WALK','WALK','RUN','JUMP','JUMP','FALL','FALL','FALL'});

imu_map = containers.Map( ...
    {'','WALKING','RUNNING','JUMPING','SITTING','SQUATTING','LIMPING','DETECTED_FALL'}, ...
    {'STILL','WALK','RUN','JUMP','SIT','SIT','LIMP','FALL'});

row_cats = {'STILL','SIT','WALK','RUN','JUMP','FALL'};
col_cats = {'STILL','SIT','WALK','RUN','JUMP','FALL','LIMP'};
row_pretty = {'Still','Sit','Walk','Run','Jump','Fall'};
col_pretty = {'Still','Sit','Walk','Run','Jump','Fall','Limp'};
nr = numel(row_cats);
nc = numel(col_cats);
cm = zeros(nr, nc);

for i = 1:height(T_imu)
    if ~isKey(act_map, T_imu.activity_label{i}) || ~isKey(imu_map, T_imu.imu_state{i})
        continue
    end
    r = find(strcmp(row_cats, act_map(T_imu.activity_label{i})));
    c = find(strcmp(col_cats, imu_map(T_imu.imu_state{i})));
    if ~isempty(r) && ~isempty(c)
        cm(r, c) = cm(r, c) + 1;
    end
end

cm_norm = cm ./ max(sum(cm, 2), 1) * 100;

figure('Color','w','Position',[100 100 750 600]);
imagesc(cm_norm); hold on;
colormap(sky);
cb = colorbar;
cb.Label.String = '% of activity packets';
cb.Label.FontSize = FS;
clim([0 100]);
xticks(1:nc); yticks(1:nr);
xticklabels(col_pretty); yticklabels(row_pretty);
xlabel('Reported IMU State'); ylabel('Actual Activity');

for r = 1:nr
    for c = 1:nc
        if cm(r,c) > 0
            col = 'k'; if cm_norm(r,c) > 50, col = 'w'; end
            text(c, r, sprintf('%.0f%%', cm_norm(r,c)), ...
                'HorizontalAlignment','center', 'Color', col, ...
                'FontSize', FS-1);
        end
    end
end
style_ax(gca, FS);


%% Helper
function style_ax(ax, fsz)
    set(ax, 'FontName', 'Helvetica', 'FontSize', fsz, ...
        'Box', 'off', 'TickDir', 'out', 'LineWidth', 1.0, ...
        'Color', 'w', 'XColor', [.2 .2 .2], 'YColor', [.2 .2 .2]);
end