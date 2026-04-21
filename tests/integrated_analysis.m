%% Config

csv_files = {'data/integrated_KH.csv'};
participant_labels = {'KH'};
% 
% csv_files = {
%     'data/integrated_P1.csv', ...
%     'data/integrated_P2.csv', ...
%     'data/integrated_P3.csv', ...
% };
% participant_labels = {'P1', 'P2', 'P3'};  % must match length of csv_files

% Set to true to also save figures as .png
save_figures = false;
output_dir   = 'figures';

% Activity label groupings
STILL_LABELS = {'PPG_WARMUP', 'BASELINE_STILL', 'RECOVERY_STILL'};
MOVE_LABELS  = {'WALK_SLOW', 'WALK_FAST', 'RUN', ...
                'JUMP_SINGLE', 'JUMP_REPEATED'};
FALL_LABELS  = {'FALL_FORWARD', 'FALL_BACKWARD', 'FALL_SIDE'};
SIT_LABELS   = {'SIT_QUICK'};

% Valid IMU states per activity label
LABEL_TO_VALID_IMU = containers.Map();
LABEL_TO_VALID_IMU('WALK_SLOW')     = {'WALKING'};
LABEL_TO_VALID_IMU('WALK_FAST')     = {'WALKING'};
LABEL_TO_VALID_IMU('RUN')           = {'RUNNING'};
LABEL_TO_VALID_IMU('JUMP_SINGLE')   = {'JUMPING'};
LABEL_TO_VALID_IMU('JUMP_REPEATED') = {'JUMPING'};
LABEL_TO_VALID_IMU('FALL_FORWARD')  = {'DETECTED_FALL', 'STATIONARY_POST_FALL'};
LABEL_TO_VALID_IMU('FALL_BACKWARD') = {'DETECTED_FALL', 'STATIONARY_POST_FALL'};
LABEL_TO_VALID_IMU('FALL_SIDE')     = {'DETECTED_FALL', 'STATIONARY_POST_FALL'};
LABEL_TO_VALID_IMU('SIT_QUICK')     = {'SITTING', 'SQUATTING'};

% Colors
C_BLUE   = [0.20 0.40 0.75];
C_ORANGE = [0.90 0.45 0.15];
C_GREEN  = [0.20 0.65 0.35];
C_RED    = [0.85 0.25 0.25];
C_GRAY   = [0.55 0.55 0.55];

% Font / size — larger for paper figures
fig_font     = 'Helvetica';
fig_fontsize = 14;
label_fontsize = 15;

bins      = {'Still', 'Moving', 'Fall', 'Sit'};
bin_order = {'Still', 'Moving', 'Fall', 'Sit', 'Other'};
bin_cols  = {C_BLUE, C_ORANGE, C_RED, C_GREEN, C_GRAY};

win_order = {"PPG_WARMUP", "BASELINE_STILL", "WALK_SLOW", "WALK_FAST", ...
             "RECOVERY_STILL", "RUN", "JUMP_SINGLE", "JUMP_REPEATED", ...
             "FALL_FORWARD", "FALL_BACKWARD", "FALL_SIDE", "SIT_QUICK"};
win_labels = {"Warmup", "Baseline", "Walk Slow", "Walk Fast", ...
              "Recovery", "Run", "Jump Single", "Jump Repeat", ...
              "Fall Fwd", "Fall Back", "Fall Side", "Sit"};

if save_figures && ~exist(output_dir, 'dir')
    mkdir(output_dir);
end

n_participants = numel(csv_files);

% Pre-allocate pooled arrays
all_paired_hr_ble   = [];
all_paired_hr_ref   = [];
all_paired_hr_bin   = {};
all_paired_spo2_ble = [];
all_paired_spo2_ref = [];
all_paired_spo2_bin = {};

all_imu_correct = 0;
all_imu_total   = 0;

% Heatmap accumulator (pooled)
row_order  = {"STILL", "SIT_QUICK", "WALK", "RUN", "JUMP", "FALL"};
row_labels = {"Still", "Sit", "Walk", "Run", "Jump", "Fall"};
col_order  = {"SITTING", "WALKING", "RUNNING", "JUMPING", "FALL_DETECTED", "LIMPING"};
col_labels = {"Sitting", "Walking", "Running", "Jumping", "Fall Detected", "Limping"};
n_rows = numel(row_order);
n_cols = numel(col_order);
hmap_counts_all = zeros(n_rows, n_cols);

% Per-participant summary storage
summary = struct();

%% Loop over participants

for p = 1:n_participants
    pid   = participant_labels{p};
    fname = csv_files{p};

    fprintf('\n%s  (%s)\n', pid, fname);

    T = readtable(fname, 'Delimiter', ',', 'TextType', 'string');

    num_cols = {'ble_hr', 'ble_spo2', 'ref_hr', 'ref_spo2', ...
                'imu_event_val', 'imu_impact', 'ble_rr', ...
                'ble_sbp', 'ble_dbp', 'ble_vbat'};
    for i = 1:numel(num_cols)
        col = num_cols{i};
        if ismember(col, T.Properties.VariableNames)
            if isstring(T.(col)) || iscellstr(T.(col))
                T.(col) = str2double(T.(col));
            end
        end
    end
    T.time = T.time - T.time(1);
    fprintf('Loaded %d rows\n', height(T));

    % Pair HR & SpO2
    paired_hr_ble   = [];  paired_hr_ref   = [];  paired_hr_bin   = {};
    paired_spo2_ble = [];  paired_spo2_ref = [];  paired_spo2_bin = {};
    paired_hr_t     = [];  paired_spo2_t   = [];

    for w = 1:numel(win_order)
        lbl_char = char(win_order{w});
        mask     = T.activity_label == win_order{w};

        if     ismember(lbl_char, STILL_LABELS), bin_name = 'Still';
        elseif ismember(lbl_char, MOVE_LABELS),  bin_name = 'Moving';
        elseif ismember(lbl_char, FALL_LABELS),  bin_name = 'Fall';
        elseif ismember(lbl_char, SIT_LABELS),   bin_name = 'Sit';
        else,                                    bin_name = 'Other';
        end

        ble_hr_rows   = find(mask & ~isnan(T.ble_hr)   & T.ble_hr   > 0);
        ble_spo2_rows = find(mask & ~isnan(T.ble_spo2) & T.ble_spo2 > 0);
        ref_hr_rows   = find(mask & ~isnan(T.ref_hr)   & T.ref_hr   > 0);
        ref_spo2_rows = find(mask & ~isnan(T.ref_spo2) & T.ref_spo2 > 0);

        for i = 1:numel(ref_hr_rows)
            if isempty(ble_hr_rows), continue; end
            t_ref = T.time(ref_hr_rows(i));
            [~, j] = min(abs(T.time(ble_hr_rows) - t_ref));
            paired_hr_ref(end+1)  = T.ref_hr(ref_hr_rows(i));   %#ok<SAGROW>
            paired_hr_ble(end+1)  = T.ble_hr(ble_hr_rows(j));   %#ok<SAGROW>
            paired_hr_bin{end+1}  = bin_name;                    %#ok<SAGROW>
            paired_hr_t(end+1)    = t_ref;                       %#ok<SAGROW>
        end

        for i = 1:numel(ref_spo2_rows)
            if isempty(ble_spo2_rows), continue; end
            t_ref = T.time(ref_spo2_rows(i));
            [~, j] = min(abs(T.time(ble_spo2_rows) - t_ref));
            paired_spo2_ref(end+1)  = T.ref_spo2(ref_spo2_rows(i)); %#ok<SAGROW>
            paired_spo2_ble(end+1)  = T.ble_spo2(ble_spo2_rows(j)); %#ok<SAGROW>
            paired_spo2_bin{end+1}  = bin_name;                      %#ok<SAGROW>
            paired_spo2_t(end+1)    = t_ref;                         %#ok<SAGROW>
        end
    end

    hr_pair_errors   = paired_hr_ble   - paired_hr_ref;
    spo2_pair_errors = paired_spo2_ble - paired_spo2_ref;
    mae_hr   = mean(abs(hr_pair_errors));
    mae_spo2 = mean(abs(spo2_pair_errors));

    fprintf('HR   MAE: %.2f bpm  (n=%d)\n', mae_hr,   numel(paired_hr_ref));
    fprintf('SpO2 MAE: %.2f %%    (n=%d)\n', mae_spo2, numel(paired_spo2_ref));

    hr_mae_per_bin   = nan(1, numel(bins));
    spo2_mae_per_bin = nan(1, numel(bins));
    for b = 1:numel(bins)
        hm = strcmp(paired_hr_bin,   bins{b});
        sm = strcmp(paired_spo2_bin, bins{b});
        if any(hm), hr_mae_per_bin(b)   = mean(abs(hr_pair_errors(hm)));   end
        if any(sm), spo2_mae_per_bin(b) = mean(abs(spo2_pair_errors(sm))); end
    end

    fprintf('%-10s  HR MAE (bpm)  SpO2 MAE (%%)\n', 'Activity');
    for b = 1:numel(bins)
        fprintf('%-10s  %12.2f  %12.2f\n', bins{b}, hr_mae_per_bin(b), spo2_mae_per_bin(b));
    end
    fprintf('%-10s  %12.2f  %12.2f\n', 'Overall', mae_hr, mae_spo2);

    % IMU classification
    imu_rows = T(T.imu_state ~= "" & ~ismissing(T.imu_state), :);
    n_correct = 0;  n_total = 0;

    imu_labels_raw = unique(imu_rows.activity_label, 'stable');
    for k = 1:numel(imu_labels_raw)
        lbl_char = char(imu_labels_raw(k));
        if ~LABEL_TO_VALID_IMU.isKey(lbl_char), continue; end
        mask_k   = imu_rows.activity_label == imu_labels_raw(k);
        states_k = imu_rows.imu_state(mask_k);
        valid    = LABEL_TO_VALID_IMU(lbl_char);
        n_correct = n_correct + sum(ismember(states_k, valid));
        n_total   = n_total   + numel(states_k);
    end
    imu_acc = n_correct / max(n_total, 1) * 100;
    fprintf('IMU accuracy: %.1f%%  (%d / %d)\n', imu_acc, n_correct, n_total);

    % Heatmap (per participant)
    imu_rows.merged_activity = imu_rows.activity_label;
    imu_rows.merged_activity(ismember(imu_rows.merged_activity, ...
        ["PPG_WARMUP","BASELINE_STILL","RECOVERY_STILL"])) = "STILL";
    imu_rows.merged_activity(ismember(imu_rows.merged_activity, ...
        ["WALK_SLOW","WALK_FAST"])) = "WALK";
    imu_rows.merged_activity(ismember(imu_rows.merged_activity, ...
        ["JUMP_SINGLE","JUMP_REPEATED"])) = "JUMP";
    imu_rows.merged_activity(ismember(imu_rows.merged_activity, ...
        ["FALL_FORWARD","FALL_BACKWARD","FALL_SIDE"])) = "FALL";

    imu_rows.merged_state = imu_rows.imu_state;
    imu_rows.merged_state(ismember(imu_rows.merged_state, ...
        ["DETECTED_FALL","STATIONARY_POST_FALL"])) = "FALL_DETECTED";
    imu_rows.merged_state(ismember(imu_rows.merged_state, ...
        ["SITTING","SQUATTING"])) = "SITTING";

    hmap_p = zeros(n_rows, n_cols);
    for r = 1:n_rows
        mask_r   = imu_rows.merged_activity == row_order{r};
        states_r = imu_rows.merged_state(mask_r);
        for c = 1:n_cols
            hmap_p(r, c) = sum(states_r == col_order{c});
        end
    end
    hmap_counts_all = hmap_counts_all + hmap_p;

    % Store summary and accumulate pooled
    summary(p).pid              = pid;
    summary(p).mae_hr           = mae_hr;
    summary(p).mae_spo2         = mae_spo2;
    summary(p).imu_acc          = imu_acc;
    summary(p).hr_mae_per_bin   = hr_mae_per_bin;
    summary(p).spo2_mae_per_bin = spo2_mae_per_bin;
    summary(p).paired_hr_ble    = paired_hr_ble;
    summary(p).paired_hr_ref    = paired_hr_ref;
    summary(p).paired_hr_bin    = paired_hr_bin;
    summary(p).paired_spo2_ble  = paired_spo2_ble;
    summary(p).paired_spo2_ref  = paired_spo2_ref;
    summary(p).paired_spo2_bin  = paired_spo2_bin;
    summary(p).hmap_counts      = hmap_p;

    % Accumulate for pooled
    all_paired_hr_ble   = [all_paired_hr_ble   paired_hr_ble];   %#ok<AGROW>
    all_paired_hr_ref   = [all_paired_hr_ref   paired_hr_ref];   %#ok<AGROW>
    all_paired_hr_bin   = [all_paired_hr_bin   paired_hr_bin];   %#ok<AGROW>
    all_paired_spo2_ble = [all_paired_spo2_ble paired_spo2_ble]; %#ok<AGROW>
    all_paired_spo2_ref = [all_paired_spo2_ref paired_spo2_ref]; %#ok<AGROW>
    all_paired_spo2_bin = [all_paired_spo2_bin paired_spo2_bin]; %#ok<AGROW>
    all_imu_correct     = all_imu_correct + n_correct;
    all_imu_total       = all_imu_total   + n_total;

    % Per-participant figures

    % HR correlation scatter
    f = figure('Position', [100 100 500 460], 'Color', 'w');
    ax = axes('Parent', f);  hold(ax, 'on');
    for b = 1:numel(bin_order)
        idx = strcmp(paired_hr_bin, bin_order{b});
        if any(idx)
            scatter(ax, paired_hr_ref(idx), paired_hr_ble(idx), 55, ...
                'o', 'MarkerFaceColor', bin_cols{b}, 'MarkerEdgeColor', 'w', ...
                'MarkerFaceAlpha', 0.85, 'LineWidth', 0.5, 'DisplayName', bin_order{b});
        end
    end
    all_hr = [paired_hr_ref paired_hr_ble];
    lims = [min(all_hr)-5, max(all_hr)+5];
    plot(ax, lims, lims, '--', 'Color', [0.6 0.6 0.6], 'LineWidth', 1.2, 'HandleVisibility', 'off');
    xlabel(ax, 'Reference HR (bpm)', 'FontSize', label_fontsize);
    ylabel(ax, 'Measured HR (bpm)',  'FontSize', label_fontsize);
    % title(ax, sprintf('%s — HR Correlation: Measured vs Reference', pid), 'FontWeight', 'bold');  % commented out for paper
    legend(ax, 'Location', 'eastoutside', 'Box', 'off', 'FontSize', fig_fontsize);
    axis(ax, 'equal');  xlim(ax, lims);  ylim(ax, lims);
    grid(ax, 'on');  ax.GridAlpha = 0.15;  ax.GridLineStyle = ':';
    style_ax(ax, fig_fontsize);
    cc = corrcoef(paired_hr_ref, paired_hr_ble);
    r2 = cc(1,2)^2;
    text(ax, lims(1)+0.03*range(lims), lims(2)-0.03*range(lims), ...
        sprintf('R^2 = %.3f,  MAE = %.1f bpm', r2, mae_hr), ...
        'FontSize', fig_fontsize-1, 'FontName', fig_font, 'VerticalAlignment', 'top', ...
        'BackgroundColor', 'w', 'EdgeColor', [0.8 0.8 0.8], 'Margin', 3);
    if save_figures
        saveas(f, fullfile(output_dir, sprintf('%s_hr_corr.png', pid)));
    end

    % SpO2 correlation scatter
    f = figure('Position', [100 100 500 460], 'Color', 'w');
    ax = axes('Parent', f);  hold(ax, 'on');
    for b = 1:numel(bin_order)
        idx = strcmp(paired_spo2_bin, bin_order{b});
        if any(idx)
            scatter(ax, paired_spo2_ref(idx), paired_spo2_ble(idx), 55, ...
                'o', 'MarkerFaceColor', bin_cols{b}, 'MarkerEdgeColor', 'w', ...
                'MarkerFaceAlpha', 0.85, 'LineWidth', 0.5, 'DisplayName', bin_order{b});
        end
    end
    all_spo2 = [paired_spo2_ref paired_spo2_ble];
    lims_s = [min(all_spo2)-max(1,range(all_spo2)*0.1), max(all_spo2)+max(1,range(all_spo2)*0.1)];
    plot(ax, lims_s, lims_s, '--', 'Color', [0.6 0.6 0.6], 'LineWidth', 1.2, 'HandleVisibility', 'off');
    xlabel(ax, 'Reference SpO_{2} (%)',  'FontSize', label_fontsize);
    ylabel(ax, 'Measured SpO_{2} (%)',   'FontSize', label_fontsize);
    % title(ax, sprintf('%s — SpO2 Correlation: Measured vs Reference', pid), 'FontWeight', 'bold');  % commented out for paper
    legend(ax, 'Location', 'eastoutside', 'Box', 'off', 'FontSize', fig_fontsize);
    axis(ax, 'equal');  xlim(ax, lims_s);  ylim(ax, lims_s);
    grid(ax, 'on');  ax.GridAlpha = 0.15;  ax.GridLineStyle = ':';
    style_ax(ax, fig_fontsize);
    cc_s = corrcoef(paired_spo2_ref, paired_spo2_ble);
    r2_s = cc_s(1,2)^2;
    text(ax, lims_s(1)+0.03*range(lims_s), lims_s(2)-0.03*range(lims_s), ...
        sprintf('R^2 = %.3f,  MAE = %.1f %%', r2_s, mae_spo2), ...
        'FontSize', fig_fontsize-1, 'FontName', fig_font, 'VerticalAlignment', 'top', ...
        'BackgroundColor', 'w', 'EdgeColor', [0.8 0.8 0.8], 'Margin', 3);
    if save_figures
        saveas(f, fullfile(output_dir, sprintf('%s_spo2_corr.png', pid)));
    end

    % IMU heatmap
    hmap_pct_p = hmap_p ./ max(sum(hmap_p, 2), 1) * 100;
    f = figure('Position', [100 100 800 500], 'Color', 'w');
    imagesc(hmap_pct_p);  colormap(sky);
    cb = colorbar;
    cb.Label.String   = '% of activity packets';
    cb.Label.FontSize = fig_fontsize;
    clim([0 100]);
    set(gca, 'XTick', 1:n_cols, 'XTickLabel', col_labels, 'XTickLabelRotation', 35, ...
             'YTick', 1:n_rows, 'YTickLabel', row_labels, 'TickLabelInterpreter', 'none');
    hold on;
    plot([0.5 n_cols+0.5], [1.5 1.5], '--', 'Color', [0.5 0.5 0.5], 'LineWidth', 1.2);
    xlabel('Reported IMU State',  'FontSize', label_fontsize);
    ylabel('Protocol Activity',   'FontSize', label_fontsize);
    % title(sprintf('%s — IMU State Distribution per Activity', pid), 'FontWeight', 'bold');  % commented out for paper
    style_ax(gca, fig_fontsize);
    annotate_heatmap(hmap_p, hmap_pct_p, n_rows, n_cols, fig_font, fig_fontsize);
    if save_figures
        saveas(f, fullfile(output_dir, sprintf('%s_imu_heatmap.png', pid)));
    end

end  % participant loop

%% Pooled overall figures (skipped when only one participant)

if n_participants > 1

    fprintf('\nPooled overall\n');

    all_hr_errors   = all_paired_hr_ble   - all_paired_hr_ref;
    all_spo2_errors = all_paired_spo2_ble - all_paired_spo2_ref;
    mae_hr_all      = mean(abs(all_hr_errors));
    mae_spo2_all    = mean(abs(all_spo2_errors));
    imu_acc_all     = all_imu_correct / max(all_imu_total, 1) * 100;

    fprintf('HR   MAE: %.2f bpm  (n=%d)\n', mae_hr_all,   numel(all_paired_hr_ref));
    fprintf('SpO2 MAE: %.2f %%    (n=%d)\n', mae_spo2_all, numel(all_paired_spo2_ref));
    fprintf('IMU accuracy: %.1f%%  (%d / %d)\n', imu_acc_all, all_imu_correct, all_imu_total);

    % Per-bin MAE (pooled)
    hr_mae_all_bin   = nan(1, numel(bins));
    spo2_mae_all_bin = nan(1, numel(bins));
    for b = 1:numel(bins)
        hm = strcmp(all_paired_hr_bin,   bins{b});
        sm = strcmp(all_paired_spo2_bin, bins{b});
        if any(hm), hr_mae_all_bin(b)   = mean(abs(all_hr_errors(hm)));   end
        if any(sm), spo2_mae_all_bin(b) = mean(abs(all_spo2_errors(sm))); end
    end

    fprintf('%-10s  HR MAE (bpm)  SpO2 MAE (%%)\n', 'Activity');
    for b = 1:numel(bins)
        fprintf('%-10s  %12.2f  %12.2f\n', bins{b}, hr_mae_all_bin(b), spo2_mae_all_bin(b));
    end
    fprintf('%-10s  %12.2f  %12.2f\n', 'Overall', mae_hr_all, mae_spo2_all);

    % Pooled HR correlation
    f = figure('Position', [100 100 500 460], 'Color', 'w');
    ax = axes('Parent', f);  hold(ax, 'on');
    for b = 1:numel(bin_order)
        idx = strcmp(all_paired_hr_bin, bin_order{b});
        if any(idx)
            scatter(ax, all_paired_hr_ref(idx), all_paired_hr_ble(idx), 55, ...
                'o', 'MarkerFaceColor', bin_cols{b}, 'MarkerEdgeColor', 'w', ...
                'MarkerFaceAlpha', 0.75, 'LineWidth', 0.5, 'DisplayName', bin_order{b});
        end
    end
    all_hr = [all_paired_hr_ref all_paired_hr_ble];
    lims = [min(all_hr)-5, max(all_hr)+5];
    plot(ax, lims, lims, '--', 'Color', [0.6 0.6 0.6], 'LineWidth', 1.2, 'HandleVisibility', 'off');
    xlabel(ax, 'Reference HR (bpm)', 'FontSize', label_fontsize);
    ylabel(ax, 'Measured HR (bpm)',  'FontSize', label_fontsize);
    % title(ax, 'Pooled — HR Correlation: Measured vs Reference', 'FontWeight', 'bold');  % commented out for paper
    legend(ax, 'Location', 'eastoutside', 'Box', 'off', 'FontSize', fig_fontsize);
    axis(ax, 'equal');  xlim(ax, lims);  ylim(ax, lims);
    grid(ax, 'on');  ax.GridAlpha = 0.15;  ax.GridLineStyle = ':';
    style_ax(ax, fig_fontsize);
    cc = corrcoef(all_paired_hr_ref, all_paired_hr_ble);
    r2 = cc(1,2)^2;
    text(ax, lims(1)+0.03*range(lims), lims(2)-0.03*range(lims), ...
        sprintf('R^2 = %.3f,  MAE = %.1f bpm', r2, mae_hr_all), ...
        'FontSize', fig_fontsize-1, 'FontName', fig_font, 'VerticalAlignment', 'top', ...
        'BackgroundColor', 'w', 'EdgeColor', [0.8 0.8 0.8], 'Margin', 3);
    if save_figures
        saveas(f, fullfile(output_dir, 'pooled_hr_corr.png'));
    end

    % Pooled SpO2 correlation
    f = figure('Position', [100 100 500 460], 'Color', 'w');
    ax = axes('Parent', f);  hold(ax, 'on');
    for b = 1:numel(bin_order)
        idx = strcmp(all_paired_spo2_bin, bin_order{b});
        if any(idx)
            scatter(ax, all_paired_spo2_ref(idx), all_paired_spo2_ble(idx), 55, ...
                'o', 'MarkerFaceColor', bin_cols{b}, 'MarkerEdgeColor', 'w', ...
                'MarkerFaceAlpha', 0.75, 'LineWidth', 0.5, 'DisplayName', bin_order{b});
        end
    end
    all_spo2 = [all_paired_spo2_ref all_paired_spo2_ble];
    lims_s = [min(all_spo2)-max(1,range(all_spo2)*0.1), max(all_spo2)+max(1,range(all_spo2)*0.1)];
    plot(ax, lims_s, lims_s, '--', 'Color', [0.6 0.6 0.6], 'LineWidth', 1.2, 'HandleVisibility', 'off');
    xlabel(ax, 'Reference SpO_{2} (%)',  'FontSize', label_fontsize);
    ylabel(ax, 'Measured SpO_{2} (%)',   'FontSize', label_fontsize);
    % title(ax, 'Pooled — SpO2 Correlation: Measured vs Reference', 'FontWeight', 'bold');  % commented out for paper
    legend(ax, 'Location', 'eastoutside', 'Box', 'off', 'FontSize', fig_fontsize);
    axis(ax, 'equal');  xlim(ax, lims_s);  ylim(ax, lims_s);
    grid(ax, 'on');  ax.GridAlpha = 0.15;  ax.GridLineStyle = ':';
    style_ax(ax, fig_fontsize);
    cc_s = corrcoef(all_paired_spo2_ref, all_paired_spo2_ble);
    r2_s = cc_s(1,2)^2;
    text(ax, lims_s(1)+0.03*range(lims_s), lims_s(2)-0.03*range(lims_s), ...
        sprintf('R^2 = %.3f,  MAE = %.1f %%', r2_s, mae_spo2_all), ...
        'FontSize', fig_fontsize-1, 'FontName', fig_font, 'VerticalAlignment', 'top', ...
        'BackgroundColor', 'w', 'EdgeColor', [0.8 0.8 0.8], 'Margin', 3);
    if save_figures
        saveas(f, fullfile(output_dir, 'pooled_spo2_corr.png'));
    end

    % Pooled IMU heatmap
    hmap_pct_all = hmap_counts_all ./ max(sum(hmap_counts_all, 2), 1) * 100;
    f = figure('Position', [100 100 800 500], 'Color', 'w');
    imagesc(hmap_pct_all);  colormap(sky);
    cb = colorbar;
    cb.Label.String   = '% of activity packets';
    cb.Label.FontSize = fig_fontsize;
    clim([0 100]);
    set(gca, 'XTick', 1:n_cols, 'XTickLabel', col_labels, 'XTickLabelRotation', 35, ...
             'YTick', 1:n_rows, 'YTickLabel', row_labels, 'TickLabelInterpreter', 'none');
    hold on;
    plot([0.5 n_cols+0.5], [1.5 1.5], '--', 'Color', [0.5 0.5 0.5], 'LineWidth', 1.2);
    xlabel('Reported IMU State', 'FontSize', label_fontsize);
    ylabel('Protocol Activity',  'FontSize', label_fontsize);
    % title('Pooled — IMU State Distribution per Activity', 'FontWeight', 'bold');  % commented out for paper
    style_ax(gca, fig_fontsize);
    annotate_heatmap(hmap_counts_all, hmap_pct_all, n_rows, n_cols, fig_font, fig_fontsize);
    if save_figures
        saveas(f, fullfile(output_dir, 'pooled_imu_heatmap.png'));
    end

    % Summary table

    fprintf('\nSummary\n');
    fprintf('%-6s  %12s  %13s  %12s\n', 'ID', 'HR MAE (bpm)', 'SpO2 MAE (%)', 'IMU Acc (%)');
    for p = 1:n_participants
        fprintf('%-6s  %12.2f  %13.2f  %12.1f\n', ...
            summary(p).pid, summary(p).mae_hr, summary(p).mae_spo2, summary(p).imu_acc);
    end
    fprintf('%-6s  %12.2f  %13.2f  %12.1f\n', 'ALL', mae_hr_all, mae_spo2_all, imu_acc_all);

end  % n_participants > 1

fprintf('\nDone.\n');


% Estimated vs true HR and SpO2 across activity windows

    % Get start/end time of each activity window that actually has paired data
    win_centers = [];
    win_edges   = [];
    win_ticks   = {};
    for w = 1:numel(win_order)
        mask_w = T.activity_label == win_order{w};
        if ~any(mask_w), continue; end
        t_w = T.time(mask_w);
        t_start = min(t_w);
        t_end   = max(t_w);

        % Skip this window if no paired HR and no paired SpO2 fall inside it
        in_hr   = any(paired_hr_t   >= t_start & paired_hr_t   <= t_end);
        in_spo2 = any(paired_spo2_t >= t_start & paired_spo2_t <= t_end);
        if ~in_hr && ~in_spo2, continue; end

        win_centers(end+1) = (t_start + t_end) / 2;     %#ok<SAGROW>
        win_edges(end+1)   = t_end;                     %#ok<SAGROW>
        win_ticks{end+1}   = win_labels{w};             %#ok<SAGROW>
    end

    f = figure('Position', [100 100 900 600], 'Color', 'w');

    % HR subplot
    ax1 = subplot(2,1,1);  hold(ax1, 'on');
    plot(ax1, paired_hr_t, paired_hr_ref, 'k-o', ...
        'LineWidth', 1.5, 'MarkerSize', 5, 'DisplayName', 'Reference HR');
    plot(ax1, paired_hr_t, paired_hr_ble, 'r--s', ...
        'LineWidth', 1.5, 'MarkerSize', 5, 'DisplayName', 'Measured HR');
    for e = 1:numel(win_edges)-1
        xline(ax1, win_edges(e), ':', 'Color', [0.7 0.7 0.7], ...
            'HandleVisibility', 'off');
    end
    ylabel(ax1, 'Heart Rate (bpm)', 'FontSize', label_fontsize);
    legend(ax1, 'Location', 'best', 'Box', 'off', 'FontSize', fig_fontsize);
    grid(ax1, 'on');  ax1.GridAlpha = 0.15;  ax1.GridLineStyle = ':';
    style_ax(ax1, fig_fontsize);
    set(ax1, 'XTick', win_centers, 'XTickLabel', win_ticks, ...
             'XTickLabelRotation', 35, 'TickLabelInterpreter', 'none');

    % SpO2 subplot
    ax2 = subplot(2,1,2);  hold(ax2, 'on');
    plot(ax2, paired_spo2_t, paired_spo2_ref, 'k-o', ...
        'LineWidth', 1.5, 'MarkerSize', 5, 'DisplayName', 'Reference SpO_{2}');
    plot(ax2, paired_spo2_t, paired_spo2_ble, 'r--s', ...
        'LineWidth', 1.5, 'MarkerSize', 5, 'DisplayName', 'Measured SpO_{2}');
    for e = 1:numel(win_edges)-1
        xline(ax2, win_edges(e), ':', 'Color', [0.7 0.7 0.7], ...
            'HandleVisibility', 'off');
    end
    ylabel(ax2, 'SpO_{2} (%)', 'FontSize', label_fontsize);
    legend(ax2, 'Location', 'best', 'Box', 'off', 'FontSize', fig_fontsize);
    grid(ax2, 'on');  ax2.GridAlpha = 0.15;  ax2.GridLineStyle = ':';
    style_ax(ax2, fig_fontsize);
    set(ax2, 'XTick', win_centers, 'XTickLabel', win_ticks, ...
             'XTickLabelRotation', 35, 'TickLabelInterpreter', 'none');

    linkaxes([ax1 ax2], 'x');
    xlim(ax1, [0 max([paired_hr_t paired_spo2_t])]);

    if save_figures
        saveas(f, fullfile(output_dir, sprintf('%s_hr_spo2_vs_window.png', pid)));
    end

%% Estimated vs true HR and SpO2 across activity windows

    % Get start/end time of each activity window that actually has paired data
    win_centers = [];
    win_edges   = [];
    win_ticks   = {};
    for w = 1:numel(win_order)
        mask_w = T.activity_label == win_order{w};
        if ~any(mask_w), continue; end
        t_w = T.time(mask_w);
        t_start = min(t_w);
        t_end   = max(t_w);

        % Skip this window if no paired HR and no paired SpO2 fall inside it
        in_hr   = any(paired_hr_t   >= t_start & paired_hr_t   <= t_end);
        in_spo2 = any(paired_spo2_t >= t_start & paired_spo2_t <= t_end);
        if ~in_hr && ~in_spo2, continue; end

        win_centers(end+1) = (t_start + t_end) / 2;     %#ok<SAGROW>
        win_edges(end+1)   = t_end;                     %#ok<SAGROW>
        win_ticks{end+1}   = win_labels{w};             %#ok<SAGROW>
    end

    f = figure('Position', [100 100 900 600], 'Color', 'w');

    % HR subplot
    ax1 = subplot(2,1,1);  hold(ax1, 'on');
    plot(ax1, paired_hr_t, paired_hr_ref, 'k-o', ...
        'LineWidth', 1.5, 'MarkerSize', 5, 'DisplayName', 'Reference HR');
    plot(ax1, paired_hr_t, paired_hr_ble, 'r--s', ...
        'LineWidth', 1.5, 'MarkerSize', 5, 'DisplayName', 'Measured HR');
    for e = 1:numel(win_edges)-1
        xline(ax1, win_edges(e), ':', 'Color', [0.7 0.7 0.7], ...
            'HandleVisibility', 'off');
    end
    ylabel(ax1, 'Heart Rate (bpm)', 'FontSize', label_fontsize);
    legend(ax1, 'Location', 'best', 'Box', 'off', 'FontSize', fig_fontsize);
    grid(ax1, 'on');  ax1.GridAlpha = 0.15;  ax1.GridLineStyle = ':';
    style_ax(ax1, fig_fontsize);
    set(ax1, 'XTick', win_centers, 'XTickLabel', win_ticks, ...
             'XTickLabelRotation', 35, 'TickLabelInterpreter', 'none');

    % SpO2 subplot
    ax2 = subplot(2,1,2);  hold(ax2, 'on');
    plot(ax2, paired_spo2_t, paired_spo2_ref, 'k-o', ...
        'LineWidth', 1.5, 'MarkerSize', 5, 'DisplayName', 'Reference SpO_{2}');
    plot(ax2, paired_spo2_t, paired_spo2_ble, 'r--s', ...
        'LineWidth', 1.5, 'MarkerSize', 5, 'DisplayName', 'Measured SpO_{2}');
    for e = 1:numel(win_edges)-1
        xline(ax2, win_edges(e), ':', 'Color', [0.7 0.7 0.7], ...
            'HandleVisibility', 'off');
    end
    ylabel(ax2, 'SpO_{2} (%)', 'FontSize', label_fontsize);
    legend(ax2, 'Location', 'best', 'Box', 'off', 'FontSize', fig_fontsize);
    grid(ax2, 'on');  ax2.GridAlpha = 0.15;  ax2.GridLineStyle = ':';
    style_ax(ax2, fig_fontsize);
    set(ax2, 'XTick', win_centers, 'XTickLabel', win_ticks, ...
             'XTickLabelRotation', 35, 'TickLabelInterpreter', 'none');

    linkaxes([ax1 ax2], 'x');
    xlim(ax1, [0 max([paired_hr_t paired_spo2_t])]);

    if save_figures
        saveas(f, fullfile(output_dir, sprintf('%s_hr_spo2_vs_window.png', pid)));
    end

%% Helpers

function style_ax(ax, fsz)
    set(ax, 'FontName', 'Helvetica', 'FontSize', fsz, ...
        'Box', 'off', 'TickDir', 'out', 'LineWidth', 1.0, ...
        'Color', 'w', 'XColor', [.2 .2 .2], 'YColor', [.2 .2 .2]);
end

function annotate_heatmap(counts, pct, nr, nc, fnt, fsz)
    for r = 1:nr
        for c = 1:nc
            if counts(r, c) > 0
                txt_col = [.15 .15 .15];
                if pct(r, c) > 55, txt_col = [1 1 1]; end
                text(c, r, sprintf('%.0f%%', pct(r, c)), ...
                    'HorizontalAlignment', 'center', 'FontSize', fsz-2, ...
                    'FontName', fnt, 'Color', txt_col);
            end
        end
    end
end
