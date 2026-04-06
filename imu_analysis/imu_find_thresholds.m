clear; clc;

tags = ["fall","run","walk","limp","jump","sit","squat"];
all_idx_sizes = [];

% currently only looking at first samples of each csv file, not each distinct window
% of data
% data that has event labels
% folders_to_search = [
%     "data/raw/shanaya"
%     "data/raw/lilly"
%     "data/raw/iris"
%     "data/raw/harry"
% ];

% data with most-ish updated thresholds being used - for perf checking
% folders_to_search = [
%     "data/split/iris"
%     "data/split/shanaya"
%     "data/split/harry"
% ];

% all serially sampled data, separated into event windows - for determining event thresholds
folders_to_search = [
    "data/split/shanaya"
    "data/split/lilly"
    "data/split/iris"
    "data/split/harry"
];

no_event_cnt = 0;
event_file_paths = [];
% Constants
% BUF_SIZE = 200;
% DEV_BUFFER_SIZE = 50;
% CHECK_TRIGGER = 1.4;
% IDLE_TRIGGER = 0.85;
% ACCEL_DEV_THRESHOLD = 0.08;
% GYRO_DEV_THRESHOLD = 17.1;
% TILT_TRIGGER = 30;
% ACCEL_DEV_WALKING = 0.13;
% ACCEL_DEV_RUNNING = 0.9;
% ASVM_RUN_WALK_THRESHOLD = 3.459;

BUF_SIZE = 200;
IDLE_TRIGGER = 0.8;
CHECK_TRIGGER = 1.4;
ACCEL_DEV_THRESHOLD = 0.08; % 0.1 in the paper, 0.0845 max from data
GYRO_DEV_THRESHOLD = 17.1; % 10 in the paper, 17ish from data
DEV_BUFFER_SIZE = 50; % same as paper
ACCEL_DEV_WALKING = 0.13;
ACCEL_DEV_RUNNING = 0.702;
ASVM_RUN_WALK_THRESHOLD = 2.6;
BUF_SMALL = 50; % calculate these things over a smaller buffer to improve responsiveness
PEAK_BUF_SIZE = 10;
% relative comparison, check if final - init angle is greater than the threshold
TILT_TRIGGER = 30;
STATIONARY_THRESHOLD = 0.15;
LIMP_SKEWNESS_THRESHOLD = 1.5;

set(groot, 'defaultTextInterpreter', 'none');        % titles, labels
set(groot, 'defaultAxesTickLabelInterpreter', 'none'); % tick labels
set(groot, 'defaultLegendInterpreter', 'none');     % legends

%% ------------------------------------------------------------
% Collect all CSV files first
%% ------------------------------------------------------------

all_files = [];

for f = 1:length(folders_to_search)

    files = dir(fullfile(folders_to_search(f),"*.csv"));

    for k = 1:length(files)

        files(k).folder = folders_to_search(f);

    end

    all_files = [all_files; files];

end

file_names = string({all_files.name});
file_paths = fullfile(string({all_files.folder}),string({all_files.name}));

%% ------------------------------------------------------------
% Preallocate result container
%% ------------------------------------------------------------

results = struct();

% Global arrays for feature-space visualization
all_ASVM_STD  = [];
all_GSVM_STD  = [];
all_AVG_ANGLE = [];
all_INIT_ANGLE = [];
all_MAX_ASVM  = [];
all_MIN_ASVM  = [];
all_SKEWNESS = [];
all_REPORTED_EVENT = [];

group_labels  = strings(0);

for t = 1:length(tags)

    tag = tags(t);

    % Find files matching tag
    tag_mask = contains(file_names,tag);

    tag_files = file_paths(tag_mask);

    n = length(tag_files);

    if n == 0
        continue
    end

    % Preallocate arrays (vectorized friendly)
    ASVM_STD   = nan(n,1);
    GSVM_STD   = nan(n,1);
    AVG_ANGLE  = nan(n,1);
    INIT_ANGLE = nan(n,1);
    MAX_ASVM   = nan(n,1);
    MIN_ASVM   = nan(n,1);
    SKEWNESS  = nan(n,1);
    REPORTED_EVENT = strings(n,1);

    for i = 1:n
        T0_init = readtable(tag_files{i});

        % remove duplicate rows
        dataCols = T0_init.Properties.VariableNames( ...
            varfun(@isnumeric,T0_init,'OutputFormat','uniform'));

        D0 = T0_init{:,dataCols};
        idx = [true; any(diff(D0) ~= 0,2)];
        eventRows = ~strcmp(T0_init.FALL_STATE(2:end), T0_init.FALL_STATE(1:end-1)) | T0_init.FALL_EVENT(2:end) ~= T0_init.FALL_EVENT(1:end-1);
        idx(2:end) = idx(2:end) | eventRows;
        T0 = T0_init(idx,:);

        % ----------------------------------------------------
        % Detect event
        % ----------------------------------------------------

        % get the reported event too
        rep_event_idx = 1 + find(((T0.FALL_STATE == "ANALYZE_IMPACT") | (T0.FALL_STATE == "STABILIZE_FALL")), 1, 'first')
        if(rep_event_idx > length(T0.FALL_STATE))
            disp("rep event idx out of bounds")
            continue
        end
        if(isempty(rep_event_idx)) 
            disp("!!!!!!!!!!!!!!NO REP EVENT IDX!!!!!!!!!")
            no_event_cnt = no_event_cnt + 1;
        else 
            event = T0.FALL_STATE{rep_event_idx};
            if(event == "POSTURE_CHECK_FALL")
                disp("event is a fall or sit/jump");
                rep_event_idx = rep_event_idx + 1; % make up for changes in imu logic
            end
            REPORTED_EVENT(i) = T0.FALL_STATE{rep_event_idx};
        end
        
        % after loading T0, detect start differently based on folder
        if contains(tag_files{i}, "full_fsm_serial_test_1_lilly") || ...
           contains(tag_files{i}, "serial_data_test")
            % old data - no state logic, fall back to threshold detection
            idle_trigger = find(T0.ASVM <= IDLE_TRIGGER, 1, 'first');
            if isempty(idle_trigger)
                disp("NO IDLE TRIGGER")
                continue
            end
        else
            % new data - use IDLE_FALL -> CHECK_FALL state transition as start
            idle_trigger = find( ...
                strcmp(T0.FALL_STATE(1:end-1), 'IDLE_FALL') & ...
                strcmp(T0.FALL_STATE(2:end),   'CHECK_FALL'), 1, 'first');
            if isempty(idle_trigger)
                disp("NO STATE TRANSITION FOUND")
                continue
            end
        end
        
        end_idx = min(idle_trigger + BUF_SIZE, height(T0));
        all_idx_sizes = [all_idx_sizes ; end_idx - idle_trigger];
        if(end_idx - idle_trigger < BUF_SIZE)
            disp("fall window too short, skipping: " + tag_files{i});
            continue
        end
        % idle_trigger = find(T0.ASVM <= IDLE_TRIGGER,1,'first');
        % 
        % if isempty(idle_trigger)
        %     disp("NO IDLE TRIGGER")
        %     continue
        % end
        % 
        % end_idx = min(idle_trigger + BUF_SIZE, height(T0));

        % make sure to only search within the buffer size
        check_idx = find(T0.ASVM(idle_trigger:end_idx) >= CHECK_TRIGGER,1,'first');
        disp(check_idx)
        disp(tag_files{i})
        if isempty(check_idx)
            continue
        end

        check_trigger = idle_trigger + check_idx;

        fall_idx = idle_trigger + 1:end_idx;

        fall_sample = T0.ASVM(fall_idx);
        fall_sample_g = T0.GSVM(fall_idx);

        fall_ax = T0.AX(fall_idx);
        fall_ay = T0.AY(fall_idx);
        fall_az = T0.AZ(fall_idx);

        % ----------------------------------------------------
        % Metrics
        % ----------------------------------------------------

        % std deviation (last DEV_BUFFER_SIZE samples)
        ASVM_STD(i) = std(fall_sample(end-DEV_BUFFER_SIZE + 1:end));
        GSVM_STD(i) = std(fall_sample_g(end-DEV_BUFFER_SIZE + 1:end));
     
        % min / max
        [MAX_ASVM(i), max_pos] = max(fall_sample);
        MIN_ASVM(i) = min(fall_sample);

        % tilt angle
        xz_dist = sqrt(fall_ax.^2 + fall_az.^2);
        horiz_angle = atan2(fall_ay,xz_dist) * (180/pi);

        ang_bound = max_pos + 50;
        if(ang_bound > 200)
            ang_bound = 200;
        end
        AVG_ANGLE(i) = mean(horiz_angle(max_pos : ang_bound));
        % AVG_ANGLE(i) = mean(horiz_angle(check_idx: ang_bound));
        INIT_ANGLE(i) = mean(horiz_angle(1:check_idx));
     

        % Ratio of values above : below 1-ish
        % AVG_ASVM(i) = length(find(fall_sample > 1)) / length(find(fall_sample < 1));
        % AVG_ASVM(i) = length(find(fall_sample > 1.1)) / length(find(fall_sample < 0.9));
 
        midpoint = median(fall_sample);
        above_dev = mean(fall_sample(fall_sample > midpoint) - midpoint);
        below_dev = mean(midpoint - fall_sample(fall_sample < midpoint));
        SKEWNESS(i) = above_dev / below_dev;
        

        disp(SKEWNESS(i))
        % post-event ASVM
    %     post_start = check_trigger + BUF_SIZE;
    % 
    %     if post_start < height(T0)
    % 
    %         post_end = min(post_start + BUF_SIZE, height(T0));
    % 
    %         AVG_ASVM(i) = mean(T0.ASVM(post_start:post_end));
    % 
    %     end
    % 
    end

    % Remove NaNs from failed detections
    valid = ~isnan(ASVM_STD);
    
    % Append valid samples to global arrays
    all_ASVM_STD  = [all_ASVM_STD;  ASVM_STD(valid)];
    all_GSVM_STD  = [all_GSVM_STD;  GSVM_STD(valid)];
    all_AVG_ANGLE = [all_AVG_ANGLE; AVG_ANGLE(valid)];
    all_INIT_ANGLE = [all_INIT_ANGLE; INIT_ANGLE(valid)];
    all_MAX_ASVM  = [all_MAX_ASVM;  MAX_ASVM(valid)];
    all_MIN_ASVM  = [all_MIN_ASVM;  MIN_ASVM(valid)];
    all_SKEWNESS = [all_SKEWNESS; SKEWNESS(valid)];
    all_REPORTED_EVENT = [all_REPORTED_EVENT; REPORTED_EVENT(valid)];
    event_file_paths = [event_file_paths; tag_files(valid)'];
    
    % Add labels for these samples
    group_labels  = [group_labels; repmat(tag,sum(valid),1)];

    results.(tag).ASVM_STD  = mean(ASVM_STD(valid));
    results.(tag).GSVM_STD  = mean(GSVM_STD(valid));
    results.(tag).AVG_ANGLE = mean(AVG_ANGLE(valid));
    results.(tag).MAX_ASVM  = mean(MAX_ASVM(valid));
    results.(tag).INIT_ANGLE = mean(INIT_ANGLE(valid));
    results.(tag).MIN_ASVM  = mean(MIN_ASVM(valid));
    results.(tag).SKEWNESS = mean(SKEWNESS(valid));
    results.(tag).N = sum(valid);

end

%% Display correlation results
figure

subplot(2,2,1)
gscatter(all_ASVM_STD, all_GSVM_STD, group_labels)
xlabel("ASVM STD")
ylabel("GSVM STD")
title("Stabilize period motion STDs")
legend('NumColumns', 2);

subplot(2,2,2)
gscatter(all_ASVM_STD, abs(all_AVG_ANGLE - all_INIT_ANGLE), group_labels)
xlabel("ASVM STD")
ylabel("Angle Diff")
title("Stabilize ASVM STD vs angle delta")
legend('NumColumns', 2);

subplot(2,2,3)
gscatter(all_ASVM_STD, all_MAX_ASVM, group_labels)
xlabel("ASVM STD")
ylabel("Max ASVM")
title("Impact Magnitude and Stabilize ASVM STD")
legend('NumColumns', 2);

subplot(2,2,4)
gscatter(all_SKEWNESS, abs(all_AVG_ANGLE - all_INIT_ANGLE), group_labels)
xlabel("AVG ASVM")
ylabel("Angle Diff")
title("Angle Delta vs avg ASVM")
legend('NumColumns', 2);

%% Plot grouped bar chart with error bars
stats_names = ["ASVM_STD","GSVM_STD","AVG_ANGLE","MAX_ASVM","MIN_ASVM","SKEWNESS"];
num_stats = length(stats_names);
num_tags  = length(tags);

means = zeros(num_tags, num_stats);
stds  = zeros(num_tags, num_stats);

for t = 1:num_tags
    tag = tags(t);
    mask = (group_labels == tag);
    if sum(mask) == 0
        continue
    end
    
    means(t,1) = mean(all_ASVM_STD(mask));
    stds(t,1)  = std(all_ASVM_STD(mask));
    
    means(t,2) = mean(all_GSVM_STD(mask));
    stds(t,2)  = std(all_GSVM_STD(mask));
    
    means(t,3) = mean(all_AVG_ANGLE(mask));
    stds(t,3)  = std(all_AVG_ANGLE(mask));
    
    means(t,4) = mean(all_MAX_ASVM(mask));
    stds(t,4)  = std(all_MAX_ASVM(mask));
    
    means(t,5) = mean(all_MIN_ASVM(mask));
    stds(t,5)  = std(all_MIN_ASVM(mask));
    
    means(t,6) = mean(all_SKEWNESS(mask));
    stds(t,6)  = std(all_SKEWNESS(mask));

    means(t,7) = mean(all_INIT_ANGLE(mask));
    stds(t,7)  = std(all_INIT_ANGLE(mask));
end

%% Plot each stat in its own subplot (3x2)
figure;

for s = 1:6
    subplot(2,3,s);
    hold on;

    if s == 3
        % Angle subplot (subplot position 3)
        % 3 bars per tag: Init, Final, Diff
        angle_means = zeros(num_tags,3);  % columns: Init, Final, Diff
        angle_stds  = zeros(num_tags,3);
    
        for t = 1:num_tags
            tag = tags(t);
            mask = (group_labels == tag);
            if sum(mask) == 0
                continue
            end
            avg_init_vals  = all_INIT_ANGLE(mask);
            avg_final_vals = all_AVG_ANGLE(mask);
            % diff_vals = abs(avg_final_vals) - abs(avg_init_vals);
            diff_vals = abs(avg_final_vals - avg_init_vals);
            
            angle_means(t,1) = mean(avg_init_vals);
            angle_means(t,2) = mean(avg_final_vals);
            angle_means(t,3) = mean(diff_vals);
            
            angle_stds(t,1) = std(avg_init_vals);
            angle_stds(t,2) = std(avg_final_vals);
            angle_stds(t,3) = std(diff_vals);
        end
    
        hb = bar(1:num_tags, angle_means);  % grouped bars
        % Get the X positions of each bar group for error bars
        x = nan(num_tags,3);
        for k = 1:3
            x(:,k) = hb(k).XEndPoints;
        end
    
        hold on
        errorbar(x, angle_means, angle_stds, 'k.', 'LineWidth', 1);
        
        yline(TILT_TRIGGER, 'r', 'LineWidth', 1);
        ylabel('Tilt Angle (deg)');
        title('Angles per tag');
        legend('INIT','FINAL','DIFF','Location','southeast');
        set(gca, 'XTick', 1:num_tags, 'XTickLabel', tags);
        grid on;
        hold off;

    else
        % Other stats: 1 bar per tag
        hb = bar(1:num_tags, means(:,s));
        errorbar(1:num_tags, means(:,s), stds(:,s), 'k.', 'LineWidth', 1);
        set(gca, 'XTick', 1:num_tags, 'XTickLabel', tags);
        ylabel(stats_names(s));
        title(stats_names(s) + " per tag");
        
        % optional thresholds
        switch stats_names(s)
            case "ASVM_STD"
                yline(ACCEL_DEV_THRESHOLD, 'red', 'LineWidth', 1);
                yline(ACCEL_DEV_WALKING, 'red', 'LineWidth', 1);
                yline(ACCEL_DEV_RUNNING, 'red', 'LineWidth', 1);
            case "GSVM_STD"
                yline(GYRO_DEV_THRESHOLD, 'red', 'LineWidth', 1);
            case "MAX_ASVM"
                yline(CHECK_TRIGGER, 'red', 'LineWidth', 1);
                yline(ASVM_RUN_WALK_THRESHOLD, 'red', 'LineWidth', 1);
            case "MIN_ASVM"
                yline(IDLE_TRIGGER, 'red', 'LineWidth', 1);
        end
        grid on;
    end

    hold off;
end

sgtitle('IMU Statistics per Event Tag');  % super title


disp(no_event_cnt)
EVENT_CLASSIFICATION_SUMMARY = [all_REPORTED_EVENT group_labels event_file_paths];

%% Classifier simulation and threshold sweep - V2

N_STD = 1.358; % 1.33;  % tune this
MIN_SCORE = 3; % 4; 
% instead of one N_STD, define per-feature multipliers
feature_weights.ASVM_STD  = 1.0;
feature_weights.GSVM_STD  = 1.0;
feature_weights.MAX_ASVM  = 0.75;  % tighter - good separator
feature_weights.MIN_ASVM  = 0.75;  % tighter - good separator
feature_weights.TILT_DIFF = 0.75;  % tighter for fall detection
feature_weights.SKEWNESS  = 1.5;   % looser - high variance

sig_tags = ["fall", "run", "walk", "limp", "jump", "sit", "squat"];
signatures = compute_signatures(group_labels, all_ASVM_STD, all_GSVM_STD, ...
    all_MAX_ASVM, all_MIN_ASVM, abs(all_AVG_ANGLE - all_INIT_ANGLE), ...
    all_SKEWNESS, N_STD, feature_weights);

%% Display signature ranges as a table for porting to microcontroller
fprintf("\n========== SIGNATURE RANGES (N_STD = %.3f) ==========\n", N_STD);

fields = {'ASVM_STD', 'GSVM_STD', 'MAX_ASVM', 'MIN_ASVM', 'TILT_DIFF', 'SKEWNESS'};
priority = ["fall", "limp", "run", "walk", "jump", "sit", "squat"];

for p = 1:length(priority)
    tag = priority(p);
    if ~isfield(signatures, tag)
        continue
    end
    fprintf("\n--- %s ---\n", upper(tag));
    fprintf("  %-12s %8s %8s %8s\n", "FEATURE", "LO", "MEAN", "HI");
    for f = 1:length(fields)
        feat = fields{f};
        sig = signatures.(tag).(feat);
        fprintf("  %-12s %8.4f %8.4f %8.4f\n", feat, sig.lo, sig.mean, sig.hi);
    end
end

fprintf("\n=====================================================\n");

% Run classifier
N_total = length(group_labels);
predictions = strings(N_total, 1);

for j = 1:N_total
    predictions(j) = classify_event_signature_scores( ...
        all_ASVM_STD(j), all_GSVM_STD(j), ...
        abs(all_AVG_ANGLE(j) - all_INIT_ANGLE(j)), ...
        all_MAX_ASVM(j), all_MIN_ASVM(j), all_SKEWNESS(j), ...
        signatures, sig_tags, MIN_SCORE);
end

norm_labels = group_labels;

correct = strcmpi(predictions, norm_labels);
fprintf("Baseline accuracy: %.1f%%\n", 100 * mean(correct));

% Per-tag accuracy
fprintf("\nPer-tag accuracy:\n");
unique_tags = unique(norm_labels);
for u = 1:length(unique_tags)
    tag_mask = norm_labels == unique_tags(u);
    tag_correct = mean(strcmpi(predictions(tag_mask), norm_labels(tag_mask)));
    fprintf("  %-10s %.1f%%  (%d/%d)\n", unique_tags(u), 100 * tag_correct, ...
        sum(strcmpi(predictions(tag_mask), norm_labels(tag_mask))), sum(tag_mask));
end

figure;
confusionchart(norm_labels, predictions);
title("Score-Based Classifier Confusion Matrix");
%% N_STD sweep
MIN_SCORE = 3;  % tune this alongside N_STD
N_STD_range = linspace(0.5, 3.0, 100);
sweep_acc   = zeros(size(N_STD_range));
sweep_fall_acc = zeros(size(N_STD_range));

for s = 1:length(N_STD_range)
    sigs_sweep = compute_signatures(group_labels, all_ASVM_STD, all_GSVM_STD, ...
        all_MAX_ASVM, all_MIN_ASVM, abs(all_AVG_ANGLE - all_INIT_ANGLE), ...
        all_SKEWNESS, N_STD_range(s));

    preds = strings(N_total, 1);
    for j = 1:N_total
        preds(j) = classify_event_signature_scores( ...
            all_ASVM_STD(j), all_GSVM_STD(j), ...
            abs(all_AVG_ANGLE(j) - all_INIT_ANGLE(j)), ...
            all_MAX_ASVM(j), all_MIN_ASVM(j), all_SKEWNESS(j), ...
            sigs_sweep, sig_tags, MIN_SCORE);
    end
    sweep_acc(s) = mean(strcmpi(preds, norm_labels));
    fall_mask = norm_labels == "fall";
    sweep_fall_acc(s) = mean(strcmpi(preds(fall_mask), norm_labels(fall_mask)));

end

figure;
hold on;
plot(N_STD_range, sweep_acc * 100, 'b', 'DisplayName', 'Overall');
plot(N_STD_range, sweep_fall_acc * 100, 'r', 'DisplayName', 'Fall only');
xline(N_STD, 'k--', 'DisplayName', 'Current N\_STD');
xlabel('N\_STD');
ylabel('Accuracy (%)');
title('Accuracy vs N\_STD (MIN\_SCORE = ' + string(MIN_SCORE) + ')');
legend('Location', 'best');
grid on;
hold off;

%% N_STD and MIN_SCORE sweep

figure;
hold on;
colors = lines(6);
for m = 1:6
    sweep_acc_m = zeros(size(N_STD_range));
    for s = 1:length(N_STD_range)
        sigs_sweep = compute_signatures(group_labels, all_ASVM_STD, all_GSVM_STD, ...
            all_MAX_ASVM, all_MIN_ASVM, abs(all_AVG_ANGLE - all_INIT_ANGLE), ...
            all_SKEWNESS, N_STD_range(s));

        preds = strings(N_total, 1);
        for j = 1:N_total
            preds(j) = classify_event_signature_scores( ...
                all_ASVM_STD(j), all_GSVM_STD(j), ...
                abs(all_AVG_ANGLE(j) - all_INIT_ANGLE(j)), ...
                all_MAX_ASVM(j), all_MIN_ASVM(j), all_SKEWNESS(j), ...
                sigs_sweep, sig_tags, m);
        end
        sweep_acc_m(s) = mean(strcmpi(preds, norm_labels));
    end
    plot(N_STD_range, sweep_acc_m * 100, 'Color', colors(m,:), ...
        'DisplayName', "MIN\_SCORE=" + m);
end
xline(N_STD, 'k--', 'DisplayName', 'Current N\_STD');
xlabel('N\_STD');
ylabel('Accuracy (%)');
title('Accuracy vs N\_STD across all MIN\_SCORE values');
legend('Location', 'best');
grid on;
hold off;

%% 
% N_STD sweep
N_STD_range = linspace(0.5, 3.0, 100);
sweep_acc   = zeros(size(N_STD_range));

for s = 1:length(N_STD_range)
    sigs_sweep = compute_signatures(group_labels, all_ASVM_STD, all_GSVM_STD, ...
        all_MAX_ASVM, all_MIN_ASVM, abs(all_AVG_ANGLE - all_INIT_ANGLE), ...
        all_SKEWNESS, N_STD_range(s), feature_weights);

    preds = strings(N_total, 1);
    for j = 1:N_total
        preds(j) = classify_event_signature_scores( ...
            all_ASVM_STD(j), all_GSVM_STD(j), ...
            abs(all_AVG_ANGLE(j) - all_INIT_ANGLE(j)), ...
            all_MAX_ASVM(j), all_MIN_ASVM(j), all_SKEWNESS(j), ...
            sigs_sweep, sig_tags, MIN_SCORE);
    end
    sweep_acc(s) = mean(strcmpi(preds, norm_labels));
end

figure;
plot(N_STD_range, sweep_acc * 100);
xline(N_STD, 'r--', 'Current');
xlabel('N\_STD multiplier');
ylabel('Accuracy (%)');
title('Accuracy vs signature width');

% add after computing predictions, before confusion matrix
fall_mask = group_labels == "fall";
fall_indices = find(fall_mask);

fprintf("\nFall misclassification breakdown:\n");
for j = 1:length(fall_indices)
    idx = fall_indices(j);
    if ~strcmpi(predictions(idx), "fall")
        sig = signatures.fall;
        fprintf("  predicted: %-6s | ASVM_STD:%.3f[%.3f-%.3f] GSVM_STD:%.1f[%.1f-%.1f] MAX:%.2f[%.2f-%.2f] MIN:%.2f[%.2f-%.2f] TILT:%.1f[%.1f-%.1f] SKEW:%.2f[%.2f-%.2f]\n", ...
            predictions(idx), ...
            all_ASVM_STD(idx),  sig.ASVM_STD.lo,  sig.ASVM_STD.hi, ...
            all_GSVM_STD(idx),  sig.GSVM_STD.lo,  sig.GSVM_STD.hi, ...
            all_MAX_ASVM(idx),  sig.MAX_ASVM.lo,  sig.MAX_ASVM.hi, ...
            all_MIN_ASVM(idx),  sig.MIN_ASVM.lo,  sig.MIN_ASVM.hi, ...
            abs(all_AVG_ANGLE(idx) - all_INIT_ANGLE(idx)), sig.TILT_DIFF.lo, sig.TILT_DIFF.hi, ...
            all_SKEWNESS(idx),  sig.SKEWNESS.lo,  sig.SKEWNESS.hi);
    end
end



%% Classifier simulation and threshold sweep - V1

thresholds.ACCEL_DEV_THRESHOLD     = 0.109; % ACCEL_DEV_THRESHOLD;
thresholds.GYRO_DEV_THRESHOLD      = 34.06; % GYRO_DEV_THRESHOLD;
thresholds.ACCEL_DEV_WALKING       = 0.041; % ACCEL_DEV_WALKING;
thresholds.ACCEL_DEV_RUNNING       = 0.5265; % ACCEL_DEV_RUNNING;
thresholds.ASVM_RUN_WALK_THRESHOLD = 3.6; % ASVM_RUN_WALK_THRESHOLD;
thresholds.TILT_TRIGGER            = 33; % TILT_TRIGGER;
thresholds.LIMP_SKEWNESS_THRESHOLD = 1.44; % 1.5;

% thresholds.ACCEL_DEV_THRESHOLD     = ACCEL_DEV_THRESHOLD;
% thresholds.GYRO_DEV_THRESHOLD      = GYRO_DEV_THRESHOLD;
% thresholds.ACCEL_DEV_WALKING       = ACCEL_DEV_WALKING;
% thresholds.ACCEL_DEV_RUNNING       = ACCEL_DEV_RUNNING;
% thresholds.ASVM_RUN_WALK_THRESHOLD = ASVM_RUN_WALK_THRESHOLD;
% thresholds.TILT_TRIGGER            = TILT_TRIGGER;
% thresholds.LIMP_SKEWNESS_THRESHOLD = 1.5;
N_total = length(group_labels);
predictions = strings(N_total, 1);

for j = 1:N_total
    predictions(j) = classify_event( ...
        all_ASVM_STD(j), all_GSVM_STD(j), ...
        abs(all_AVG_ANGLE(j) - all_INIT_ANGLE(j)), ...
        all_MAX_ASVM(j), all_SKEWNESS(j), thresholds);
end



norm_labels = group_labels;

correct = strcmpi(predictions, norm_labels);
fprintf("Baseline accuracy: %.1f%%\n", 100 * mean(correct));

% Per-tag accuracy
fprintf("\nPer-tag accuracy:\n");
unique_tags = unique(norm_labels);
for u = 1:length(unique_tags)
    tag_mask = norm_labels == unique_tags(u);
    tag_correct = mean(strcmpi(predictions(tag_mask), norm_labels(tag_mask)));
    fprintf("  %-10s %.1f%%  (%d/%d)\n", unique_tags(u), 100 * tag_correct, sum(strcmpi(predictions(tag_mask), norm_labels(tag_mask))), sum(tag_mask));
end

figure;
confusionchart(norm_labels, predictions);
title("Baseline classifier confusion matrix");

% Threshold sweep - change sweep_field to tune any threshold
sweep_field = 'GYRO_DEV_THRESHOLD';
base_val    = thresholds.(sweep_field);
sweep_range = linspace(base_val * 0.05, base_val * 3.0, 200);
sweep_acc   = zeros(size(sweep_range));

for s = 1:length(sweep_range)
    t_sweep = thresholds;
    t_sweep.(sweep_field) = sweep_range(s);

    preds = strings(N_total, 1);
    for j = 1:N_total
        preds(j) = classify_event( ...
            all_ASVM_STD(j), all_GSVM_STD(j), ...
            abs(all_AVG_ANGLE(j) - all_INIT_ANGLE(j)), ...
            all_MAX_ASVM(j), all_SKEWNESS(j), t_sweep);
    end
    sweep_acc(s) = mean(strcmpi(preds, norm_labels));
end

figure;
plot(sweep_range, sweep_acc * 100);
xline(base_val, 'r--', 'Current');
xlabel(sweep_field, 'Interpreter', 'none');
ylabel("Accuracy (%)");
title("Accuracy vs " + sweep_field);

% Classifier function

function predicted = classify_event(std_accel, std_gyro, tilt_diff, max_asvm, skewness, thresholds)

    stabilized_dev = (std_accel <= thresholds.ACCEL_DEV_THRESHOLD) && ...
                     (std_accel  <= thresholds.GYRO_DEV_THRESHOLD);
    walking_dev    = (std_accel >= thresholds.ACCEL_DEV_WALKING) && ...
                     (std_accel <= thresholds.ACCEL_DEV_RUNNING);
    running_dev    = (std_accel >= thresholds.ACCEL_DEV_RUNNING);
    running_accel  = (max_asvm  >= thresholds.ASVM_RUN_WALK_THRESHOLD);
    fall_tilt      = (tilt_diff >= thresholds.TILT_TRIGGER);
    limp           = (skewness  >= thresholds.LIMP_SKEWNESS_THRESHOLD);

    if stabilized_dev && fall_tilt
        predicted = "fall";
    elseif running_dev && ~fall_tilt && running_accel
        predicted = "run";
    elseif walking_dev && ~fall_tilt && ~running_accel
        if limp
            predicted = "limp";
        else
            predicted = "walk";
        end
    elseif stabilized_dev && ~fall_tilt
        predicted = "jump";
    else
        predicted = "idle";
    end
end





%% ------------------------------------------------------------
% Functions
%% ------------------------------------------------------------

function signatures = compute_signatures(group_labels, asvm_std, gsvm_std, ...
    max_asvm, min_asvm, tilt_diff, skewness, N_STD, feature_weights)

    sig_tags = ["fall", "run", "walk", "limp", "jump", "sit", "squat"];
    signatures = struct();

    fields = {'ASVM_STD', 'GSVM_STD', 'MAX_ASVM', 'MIN_ASVM', 'TILT_DIFF', 'SKEWNESS'};
    data   = {asvm_std, gsvm_std, max_asvm, min_asvm, tilt_diff, skewness};

    for u = 1:length(sig_tags)
        tag = sig_tags(u);
        mask = (group_labels == tag);
        if sum(mask) == 0
            continue
        end
        for f = 1:length(fields)
            vals = data{f}(mask);
            m = mean(vals);
            s = std(vals);
            % w = N_STD*feature_weights.(fields{f}) * t_weight;
            % w = N_STD * feature_weights_by_tag.(tag).(fields{f});
            w = N_STD; % for now
            signatures.(tag).(fields{f}).mean = m;
            signatures.(tag).(fields{f}).std  = s;
            signatures.(tag).(fields{f}).lo   = m - w * s;
            signatures.(tag).(fields{f}).hi   = m + w * s;
        end
    end
end

function predicted = classify_event_signature(std_accel, std_gyro, tilt_diff, ...
    max_asvm, min_asvm, skewness, signatures, sig_tags)

    in_range = @(val, sig, field) ...
        val >= sig.(field).lo && val <= sig.(field).hi;

    % priority order - fall first since it's safety critical
    priority = ["fall", "limp", "run", "walk", "jump", "sit", "squat"];
    predicted = "idle";

    for p = 1:length(priority)
        tag = priority(p);
        if ~isfield(signatures, tag)
            continue
        end
        sig = signatures.(tag);

        match = in_range(std_accel, sig, 'ASVM_STD')  && ...
                in_range(std_gyro,  sig, 'GSVM_STD')  && ...
                in_range(max_asvm,  sig, 'MAX_ASVM')  && ...
                in_range(min_asvm,  sig, 'MIN_ASVM')  && ...
                in_range(tilt_diff, sig, 'TILT_DIFF') && ...
                in_range(skewness,  sig, 'SKEWNESS');
        if match
            predicted = tag;
            return;
        end
    end
end

function predicted = classify_event_signature_scores(std_accel, std_gyro, tilt_diff, ...
    max_asvm, min_asvm, skewness, signatures, sig_tags, MIN_SCORE)

    in_range = @(val, sig, field) ...
        val >= sig.(field).lo && val <= sig.(field).hi;

    priority = ["fall", "limp", "run", "walk", "jump", "sit", "squat"];
    predicted = "idle";
    best_score = 0;

    for p = 1:length(priority)
        tag = priority(p);
        if ~isfield(signatures, tag)
            continue
        end
        sig = signatures.(tag);

        score = in_range(std_accel, sig, 'ASVM_STD') + ...
                in_range(std_gyro,  sig, 'GSVM_STD')  + ...
                in_range(max_asvm,  sig, 'MAX_ASVM')  + ...
                in_range(min_asvm,  sig, 'MIN_ASVM')  + ...
                in_range(tilt_diff, sig, 'TILT_DIFF') + ...
                in_range(skewness,  sig, 'SKEWNESS');

        if score > best_score
            best_score = score;
            predicted = tag;
        end
    end

    % require at least this many features to match
    if best_score < MIN_SCORE
        predicted = "idle";
    end
end
