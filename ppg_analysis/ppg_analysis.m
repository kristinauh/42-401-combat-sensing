% Analyze raw PPG data and reference HR/SpO2 data
%% Load data
Tppg = readtable('data/ppg_raw_KH.csv');
Tref = readtable('data/ppg_ref_KH.csv');

% Convert timestamps into datetime objects
Tppg.timestamp = datetime(Tppg.timestamp, 'InputFormat', 'yyyy-MM-dd''T''HH:mm:ss.SSS');
Tref.timestamp = datetime(Tref.timestamp, 'InputFormat', 'yyyy-MM-dd''T''HH:mm:ss.SSS');

% Get list of windows from the PPG samples file
win_ids = unique(Tppg.window);

% Choose window to analyze
window = 13;

% Initial SpO2 calibration constants
SPO2_A = 110;
SPO2_B = 25;

% Literature-based calibration constants from Chan et al. (Biosensors 2021)
% Chest reflectance at 660nm/950nm, globally trained across 20 subjects
SPO2_A_lit = 106.69;
SPO2_B_lit = 21.54;

% Trim noisy start of each window
trim_sec = 0.13;

%% Get median reference HR / SpO2 for each window

num_windows = length(win_ids);

true_hr_all = nan(num_windows,1);
true_spo2_all = nan(num_windows,1);
num_ref_all = zeros(num_windows,1);

for k = 1:num_windows
    w_k = win_ids(k);

    idx_ref = Tref.window == w_k;
    Tw_ref = Tref(idx_ref,:);

    if height(Tw_ref) == 0
        continue;
    end

    % Use median of all user-entered readings in this window
    true_hr_all(k) = median(Tw_ref.true_hr, 'omitnan');
    true_spo2_all(k) = median(Tw_ref.true_spo2, 'omitnan');
    num_ref_all(k) = height(Tw_ref);
end

%% Compute HR, R, and SpO2 for each window

est_hr_all = nan(num_windows,1);
err_hr_all = nan(num_windows,1);
fs_all = nan(num_windows,1);

R_all = [];
spo2_all = [];
win_all = [];

for k = 1:num_windows

    w_k = win_ids(k);
    Tw_k = Tppg(Tppg.window == w_k,:);

    if height(Tw_k) < 10
        continue;
    end

    if isnan(true_spo2_all(k))
        continue;
    end

    ir_raw_k = double(Tw_k.ir_raw);
    red_raw_k = double(Tw_k.red_raw);

    t_k = seconds(Tw_k.timestamp - Tw_k.timestamp(1));

    dt_k = seconds(diff(Tw_k.timestamp));
    dt_k = dt_k(dt_k > 0);

    if isempty(dt_k)
        continue;
    end

    fs_k = 1 / median(dt_k);
    fs_all(k) = fs_k;

    ir0_k = ir_raw_k - mean(ir_raw_k);
    red0_k = red_raw_k - mean(red_raw_k);

    if length(ir0_k) <= 20
        continue;
    end

    low_cut = 0.7;
    high_cut = min(3.5, 0.45 * fs_k);

    if fs_k <= 2 * low_cut || high_cut <= low_cut
        continue;
    end

    [b_k, a_k] = butter(2, [low_cut high_cut] / (fs_k/2), 'bandpass');

    ir_k = filtfilt(b_k, a_k, ir0_k);
    red_k = filtfilt(b_k, a_k, red0_k);

    ir_norm_k = ir_k / std(ir_k);

    start_idx = find(t_k >= trim_sec, 1, 'first');
    if isempty(start_idx)
        continue;
    end

    ir_k = ir_k(start_idx:end);
    red_k = red_k(start_idx:end);
    ir_raw_k = ir_raw_k(start_idx:end);
    red_raw_k = red_raw_k(start_idx:end);

    min_peak_dist = min(round(fs_k * 0.4), length(ir_k) - 2);

    if min_peak_dist > 1
        [~, locs] = findpeaks(ir_norm_k(start_idx:end), ...
            'MinPeakDistance', min_peak_dist);

        if length(locs) >= 2
            ibi = diff(locs) / fs_k;
            hr = 60 / mean(ibi);
            est_hr_all(k) = hr;
            err_hr_all(k) = hr - true_hr_all(k);
        end
    end

    % DC via low-pass filter at 0.1 Hz (Chan et al.) instead of segment mean
    lp_cut = 0.1;
    if fs_k > 2 * lp_cut
        [blp_k, alp_k] = butter(2, lp_cut / (fs_k/2), 'low');
        ir_dc_lp_k = filtfilt(blp_k, alp_k, ir_raw_k);
        red_dc_lp_k = filtfilt(blp_k, alp_k, red_raw_k);
    else
        % Fallback to mean if fs too low for 0.1 Hz filter
        ir_dc_lp_k = ir_raw_k * 0 + mean(ir_raw_k);
        red_dc_lp_k = red_raw_k * 0 + mean(red_raw_k);
    end

    seg_len = round(4 * fs_k);
    num_seg = floor(length(ir_k) / seg_len);

    for s = 1:num_seg

        idx = (s-1)*seg_len + (1:seg_len);

        ir_seg = ir_k(idx);
        red_seg = red_k(idx);

        % DC from low-pass filtered raw signal evaluated at segment
        ir_dc = mean(ir_dc_lp_k(idx));
        red_dc = mean(red_dc_lp_k(idx));

        % AC via RMS instead of peak-to-peak (more robust to noise spikes)
        ir_ac = rms(ir_seg);
        red_ac = rms(red_seg);

        if ir_dc <= 0 || red_dc <= 0 || ir_ac <= 0 || red_ac <= 0
            continue;
        end

        R_seg = (red_ac / red_dc) / (ir_ac / ir_dc);

        % SQI: cross-correlation of red vs IR segment (Chan et al.)
        % Reject segment if normalized cross-correlation peak < 0.7
        ir_seg_norm = ir_seg - mean(ir_seg);
        red_seg_norm = red_seg - mean(red_seg);
        denom = norm(ir_seg_norm) * norm(red_seg_norm);
        if denom > 0
            xc = xcorr(red_seg_norm, ir_seg_norm, 'normalized');
            ncc_max = max(xc);
        else
            ncc_max = 0;
        end

        if ncc_max < 0.7
            continue;
        end

        t_center = mean(idx)/fs_k;

        spo2_seg = interp1( ...
            seconds(Tref.timestamp(Tref.window==w_k) - ...
                    Tref.timestamp(find(Tref.window==w_k,1))), ...
            Tref.true_spo2(Tref.window==w_k), ...
            t_center, ...
            'linear', 'extrap');

        R_all(end+1,1) = R_seg;
        spo2_all(end+1,1) = spo2_seg;
        win_all(end+1,1) = w_k;
    end
end

%% Fit SpO2 calibration line: true_spo2 = A - B*R

valid_fit_idx = ~isnan(R_all) & ~isnan(spo2_all);

R_fit = R_all(valid_fit_idx);
spo2_fit = spo2_all(valid_fit_idx);

if numel(R_fit) < 2
    warning('Not enough segment-level data to fit calibration.');
    SPO2_A_fit = SPO2_A;
    SPO2_B_fit = SPO2_B;
    p = [-SPO2_B_fit, SPO2_A_fit];
else
    p = polyfit(R_fit, spo2_fit, 1);

    SPO2_A_fit = p(2);
    SPO2_B_fit = -p(1);

    disp('Fitted SpO2 calibration (segment-level):')
    disp(['  SPO2_A = ', num2str(SPO2_A_fit)])
    disp(['  SPO2_B = ', num2str(SPO2_B_fit)])
end

disp('Literature SpO2 calibration (Chan et al. 2021):')
disp(['  SPO2_A = ', num2str(SPO2_A_lit)])
disp(['  SPO2_B = ', num2str(SPO2_B_lit)])

%% Recompute SpO2 estimates using fitted and literature calibration constants

est_spo2_fit_all = nan(num_windows,1);
err_spo2_fit_all = nan(num_windows,1);
est_spo2_lit_all = nan(num_windows,1);
err_spo2_lit_all = nan(num_windows,1);

for k = 1:num_windows
    w_k = win_ids(k);

    % Average R across all segments belonging to this window
    R_win = R_all(win_all == w_k);

    if isempty(R_win) || isnan(true_spo2_all(k))
        continue;
    end

    R_k = median(R_win);

    est_spo2_fit_all(k) = SPO2_A_fit - SPO2_B_fit * R_k;
    est_spo2_fit_all(k) = min(100, est_spo2_fit_all(k));
    err_spo2_fit_all(k) = est_spo2_fit_all(k) - true_spo2_all(k);

    est_spo2_lit_all(k) = SPO2_A_lit - SPO2_B_lit * R_k;
    est_spo2_lit_all(k) = min(100, est_spo2_lit_all(k));
    err_spo2_lit_all(k) = est_spo2_lit_all(k) - true_spo2_all(k);
end

%% Summary metrics

valid_hr_idx = ~isnan(est_hr_all) & ~isnan(true_hr_all);
mae_hr = mean(abs(err_hr_all(valid_hr_idx)));

valid_spo2_idx = ~isnan(est_spo2_fit_all) & ~isnan(true_spo2_all);
mae_spo2 = mean(abs(err_spo2_fit_all(valid_spo2_idx)));

valid_spo2_lit_idx = ~isnan(est_spo2_lit_all) & ~isnan(true_spo2_all);
mae_spo2_lit = mean(abs(err_spo2_lit_all(valid_spo2_lit_idx)));

results_table = table( ...
    win_ids, num_ref_all, fs_all, ...
    est_hr_all, true_hr_all, err_hr_all, ...
    'VariableNames', {'window','num_ref','fs', ...
    'estimated_hr','true_hr','error_hr'});

disp(results_table)

segment_table = table(R_all, spo2_all, ...
    'VariableNames', {'R','spo2'});

disp(segment_table(1:min(10,height(segment_table)),:))

disp(['Mean Absolute Error (HR) = ', num2str(mae_hr), ' bpm'])
disp(['Mean Absolute Error (SpO2, polyfit) = ', num2str(mae_spo2), ' %'])
disp(['Mean Absolute Error (SpO2, literature) = ', num2str(mae_spo2_lit), ' %'])

%% Plot: window vs HR
figure
plot(win_ids(valid_hr_idx), true_hr_all(valid_hr_idx), 'k-o', 'LineWidth', 1.5, 'MarkerSize', 5)
hold on
plot(win_ids(valid_hr_idx), est_hr_all(valid_hr_idx), 'r-s', 'LineWidth', 1.5, 'MarkerSize', 5)
xlabel('Window')
ylabel('Heart Rate (bpm)')
title(sprintf('Window vs HR (median reference) | MAE = %.2f bpm', mae_hr))
legend('True HR', 'Estimated HR', 'Location', 'best')
grid on

%% Plot: window vs SpO2 using fitted calibration
figure
plot(win_ids(valid_spo2_idx), true_spo2_all(valid_spo2_idx), 'k-o', 'LineWidth', 1.5, 'MarkerSize', 5)
hold on
plot(win_ids(valid_spo2_idx), est_spo2_fit_all(valid_spo2_idx), 'b-s', 'LineWidth', 1.5, 'MarkerSize', 5)
xlabel('Window')
ylabel('SpO2 (%)')
title(sprintf('Window vs SpO2 (fitted calibration) | MAE = %.2f %%', mae_spo2))
legend('True SpO2', 'Estimated SpO2 (polyfit)', 'Location', 'best')
grid on

%% Plot: window vs SpO2 using literature calibration
figure
plot(win_ids(valid_spo2_lit_idx), true_spo2_all(valid_spo2_lit_idx), 'k-o', 'LineWidth', 1.5, 'MarkerSize', 5)
hold on
plot(win_ids(valid_spo2_lit_idx), est_spo2_lit_all(valid_spo2_lit_idx), 'm-s', 'LineWidth', 1.5, 'MarkerSize', 5)
xlabel('Window')
ylabel('SpO2 (%)')
title(sprintf('Window vs SpO2 (literature calibration) | MAE = %.2f %%', mae_spo2_lit))
legend('True SpO2', 'Estimated SpO2 (Chan et al.)', 'Location', 'best')
grid on

%% Plot SpO2 calibration fit
figure
scatter(R_fit, spo2_fit, 50, 'filled')
hold on
R_line = linspace(min(R_fit), max(R_fit), 200);
spo2_line = polyval(p, R_line);
plot(R_line, spo2_line, 'r-', 'LineWidth', 1.5)
xlabel('R = (red_{AC}/red_{DC}) / (ir_{AC}/ir_{DC})')
ylabel('True SpO2 (%)')
title('SpO2 Calibration Fit')
legend('Calibration windows', 'Fitted line', 'Location', 'best')
grid on

%% Inspect one selected window

w = win_ids(window);

% PPG data for this window
idx_ppg = Tppg.window == w;
Tw = Tppg(idx_ppg,:);

% Reference data for this window
idx_ref = Tref.window == w;
Tw_ref = Tref(idx_ref,:);

if height(Tw) < 3
    error('Selected window has too few PPG samples.')
end

if height(Tw_ref) == 0
    error('Selected window has no reference readings.')
end

true_hr_window = median(Tw_ref.true_hr, 'omitnan');
true_spo2_window = median(Tw_ref.true_spo2, 'omitnan');

% Time axis
t = seconds(Tw.timestamp - Tw.timestamp(1));

% Raw signals
ir_raw = double(Tw.ir_raw);
red_raw = double(Tw.red_raw);

% Estimate sampling rate
dt = seconds(diff(Tw.timestamp));
dt = dt(dt > 0);
fs = 1 / median(dt);

% Remove DC offset
ir0 = ir_raw - mean(ir_raw);
red0 = red_raw - mean(red_raw);

if length(ir0) <= 12 || length(red0) <= 12
    error('Selected window is too short for filtfilt.')
end

% Pulse band
low_cut = 0.7;
high_cut = min(3.5, 0.45 * fs);

if fs <= 2 * low_cut || high_cut <= low_cut
    error('Selected window has invalid or too-low sampling rate for this bandpass filter.')
end

% Filter
[b, a] = butter(2, [low_cut high_cut] / (fs/2), 'bandpass');
ir = filtfilt(b, a, ir0);
red = filtfilt(b, a, red0);

% Normalize for plotting
ir_raw_norm = (ir_raw - mean(ir_raw)) / std(ir_raw);
red_raw_norm = (red_raw - mean(red_raw)) / std(red_raw);

ir_norm = ir / std(ir);
red_norm = red / std(red);

% Trim noisy beginning
start_idx_trim = find(t >= trim_sec, 1, 'first');
if isempty(start_idx_trim)
    error('Trim time is longer than this selected window.')
end

t_trim = t(start_idx_trim:end);
ir_trim = ir(start_idx_trim:end);
red_trim = red(start_idx_trim:end);
ir_norm_trim = ir_norm(start_idx_trim:end);
ir_raw_trim = ir_raw(start_idx_trim:end);
red_raw_trim = red_raw(start_idx_trim:end);

% Detect peaks
min_peak_dist = min(round(fs * 0.4), length(ir_norm_trim) - 2);

if min_peak_dist < 1
    pks = [];
    locs = [];
else
    [pks, locs] = findpeaks(ir_norm_trim, 'MinPeakDistance', min_peak_dist);
end

% Estimate HR for this window
if length(locs) >= 2
    ibi = diff(locs) / fs;
    hr_est = 60 / mean(ibi);
    hr_err = hr_est - true_hr_window;

    disp(['Estimated HR = ', num2str(hr_est), ' bpm'])
    disp(['True HR      = ', num2str(true_hr_window), ' bpm'])
    disp(['Error        = ', num2str(hr_err), ' bpm'])
else
    hr_est = NaN;
    hr_err = NaN;
    disp('Estimated HR = not enough peaks detected')
    disp(['True HR      = ', num2str(true_hr_window), ' bpm'])
end

% DC via low-pass filter at 0.1 Hz for single window SpO2
lp_cut = 0.1;
if fs > 2 * lp_cut
    [blp, alp] = butter(2, lp_cut / (fs/2), 'low');
    ir_dc_lp = filtfilt(blp, alp, ir_raw_trim);
    red_dc_lp = filtfilt(blp, alp, red_raw_trim);
    ir_dc = mean(ir_dc_lp);
    red_dc = mean(red_dc_lp);
else
    ir_dc = mean(ir_raw_trim);
    red_dc = mean(red_raw_trim);
end

% AC via RMS of bandpass-filtered signal
ir_ac = rms(ir_trim);
red_ac = rms(red_trim);

if ir_dc > 0 && red_dc > 0 && ir_ac > 0 && red_ac > 0
    R = (red_ac / red_dc) / (ir_ac / ir_dc);

    % Estimate using both calibration methods
    spo2_est_fit = min(100, SPO2_A_fit - SPO2_B_fit * R);
    spo2_est_lit = min(100, SPO2_A_lit - SPO2_B_lit * R);

    disp(['Estimated SpO2 (polyfit)    = ', num2str(spo2_est_fit), ' %'])
    disp(['Estimated SpO2 (Chan et al) = ', num2str(spo2_est_lit), ' %'])
    disp(['True SpO2                   = ', num2str(true_spo2_window), ' %'])
    disp(['Error (polyfit)             = ', num2str(spo2_est_fit - true_spo2_window), ' %'])
    disp(['Error (Chan et al)          = ', num2str(spo2_est_lit - true_spo2_window), ' %'])

    spo2_est = spo2_est_fit;
    spo2_err = spo2_est - true_spo2_window;
else
    R = NaN;
    spo2_est = NaN;
    spo2_err = NaN;
    disp('Estimated SpO2 = could not compute')
    disp(['True SpO2      = ', num2str(true_spo2_window), ' %'])
end

% Frequency axis for FFT
N = length(ir_trim);
f = (0:floor(N/2)) * fs / N;

%% Plot raw vs filtered signals for selected window
figure

subplot(2,1,1)
plot(t, ir_raw_norm, 'Color', [0.85 0.85 0.85])
hold on
plot(t, ir_norm, 'k', 'LineWidth', 1.0)
plot(t_trim(locs), pks, 'bo')
xline(trim_sec, '--b', 'Trim Start')
xlabel('Time (s)')
ylabel('Normalized Amplitude')
title(sprintf('IR Raw vs Filtered (Window %d)', w))
legend('Raw', 'Bandpass', 'Peaks', 'Trim Start')
grid on

subplot(2,1,2)
plot(t, red_raw_norm, 'Color', [0.85 0.85 0.85])
hold on
plot(t, red_norm, 'r', 'LineWidth', 1.0)
xline(trim_sec, '--b', 'Trim Start')
xlabel('Time (s)')
ylabel('Normalized Amplitude')
title('Red Raw vs Filtered')
legend('Raw', 'Bandpass', 'Trim Start')
grid on

%% FFT of trimmed filtered signals
Y_ir = fft(ir_trim);
Y_red = fft(red_trim);

P_ir = abs(Y_ir / N);
P_ir = P_ir(1:floor(N/2)+1);

P_red = abs(Y_red / N);
P_red = P_red(1:floor(N/2)+1);

figure
plot(f, P_ir, 'k', 'LineWidth', 1.5)
hold on
plot(f, P_red, 'r', 'LineWidth', 1.5)
xlim([0 5])
xlabel('Frequency (Hz)')
ylabel('Amplitude')
title(sprintf('PPG FFT Spectrum (Window %d)', w))
legend('IR', 'Red')
grid on

%% Plot reference readings inside this selected window
% Shows multiple entered HR / SpO2 values for the same window

t_ref = seconds(Tw_ref.timestamp - Tw.timestamp(1));

figure

subplot(2,1,1)
plot(t_ref, Tw_ref.true_hr, 'ko-', 'LineWidth', 1.2, 'MarkerSize', 6)
hold on
yline(true_hr_window, '--k', 'Median True HR')
if ~isnan(hr_est)
    yline(hr_est, '--r', 'Estimated HR')
end
xlabel('Time within window (s)')
ylabel('Heart Rate (bpm)')
title(sprintf('Reference HR Readings in Window %d', w))
legend('Entered HR', 'Median True HR', 'Estimated HR', 'Location', 'best')
grid on

subplot(2,1,2)
plot(t_ref, Tw_ref.true_spo2, 'ko-', 'LineWidth', 1.2, 'MarkerSize', 6)
hold on
yline(true_spo2_window, '--k', 'Median True SpO2')
if ~isnan(spo2_est)
    yline(spo2_est, '--b', 'Estimated SpO2 (polyfit)')
end
xlabel('Time within window (s)')
ylabel('SpO2 (%)')
title(sprintf('Reference SpO2 Readings in Window %d', w))
legend('Entered SpO2', 'Median True SpO2', 'Estimated SpO2', 'Location', 'best')
grid on

%% SpO2 calibration from AC/DC ratio range mapping (88-100%)

% Find the observed R range from clean segments
R_clean = R_all(~isnan(R_all));

if numel(R_clean) < 2
    warning('Not enough R values to compute range-mapped calibration.');
else
    R_lo = prctile(R_clean, 5);   % low percentile -> high SpO2
    R_hi = prctile(R_clean, 95);  % high percentile -> low SpO2

    % Anchor: R_lo -> 100%, R_hi -> 88%
    % SpO2 = A - B*R, so:
    %   100 = A - B * R_lo
    %    88 = A - B * R_hi
    % Solving:
    %   B = (100 - 88) / (R_hi - R_lo)
    %   A = 100 + B * R_lo

    SPO2_B_range = (100 - 88) / (R_hi - R_lo);
    SPO2_A_range = 100 + SPO2_B_range * R_lo;

    disp('Range-mapped SpO2 calibration (88-100%):')
    disp(['  SPO2_A = ', num2str(SPO2_A_range)])
    disp(['  SPO2_B = ', num2str(SPO2_B_range)])

    % Plot: compare all calibration curves
    figure
    scatter(R_fit, spo2_fit, 50, 'filled', 'DisplayName', 'Calibration segments')
    hold on

    R_line = linspace(min(R_clean) - 0.05, max(R_clean) + 0.05, 200);

    % Existing polyfit curve
    spo2_line_fit = polyval(p, R_line);
    plot(R_line, spo2_line_fit, 'r-', 'LineWidth', 1.5, 'DisplayName', ...
        sprintf('Polyfit (A=%.1f, B=%.1f)', SPO2_A_fit, SPO2_B_fit))

    % Range-mapped curve
    spo2_line_range = SPO2_A_range - SPO2_B_range * R_line;
    plot(R_line, spo2_line_range, 'b--', 'LineWidth', 1.5, 'DisplayName', ...
        sprintf('Range-mapped (A=%.1f, B=%.1f)', SPO2_A_range, SPO2_B_range))

    % Literature curve (Chan et al.)
    spo2_line_lit = SPO2_A_lit - SPO2_B_lit * R_line;
    plot(R_line, spo2_line_lit, 'g-', 'LineWidth', 1.5, 'DisplayName', ...
        sprintf('Chan et al. (A=%.1f, B=%.1f)', SPO2_A_lit, SPO2_B_lit))

    % Mark range anchors
    scatter([R_lo, R_hi], [100, 88], 80, 'b', 'filled', '^', ...
        'DisplayName', 'Range anchors (5th/95th pctile)')

    xlabel('R = (red_{AC}/red_{DC}) / (ir_{AC}/ir_{DC})')
    ylabel('SpO2 (%)')
    title('SpO2 Calibration: Polyfit vs Range-Mapped vs Chan et al.')
    legend('Location', 'best')
    grid on
end

%% Shift alignment: find window offset that minimizes MAE (Chan et al. approach)
% Accounts for fingertip pulse oximeter lag relative to chest sensor
% Chan et al. reported mean finger delay of ~25-27s; Schreiner et al. up to 15s
% At ~10s windows this corresponds to a 1-3 window shift

max_shift = 4;
mae_shift_fit = nan(max_shift+1, 1);
mae_shift_lit = nan(max_shift+1, 1);

for shift = 0:max_shift

    % Shift estimated SpO2 forward: chest estimate leads the finger reference
    est_fit_shifted = nan(num_windows,1);
    est_lit_shifted = nan(num_windows,1);

    est_fit_shifted(1+shift:end) = est_spo2_fit_all(1:end-shift);
    est_lit_shifted(1+shift:end) = est_spo2_lit_all(1:end-shift);

    valid_fit_s = ~isnan(est_fit_shifted) & ~isnan(true_spo2_all);
    valid_lit_s = ~isnan(est_lit_shifted) & ~isnan(true_spo2_all);

    if sum(valid_fit_s) >= 2
        mae_shift_fit(shift+1) = mean(abs(est_fit_shifted(valid_fit_s) - true_spo2_all(valid_fit_s)));
    end
    if sum(valid_lit_s) >= 2
        mae_shift_lit(shift+1) = mean(abs(est_lit_shifted(valid_lit_s) - true_spo2_all(valid_lit_s)));
    end

    fprintf('Shift = %d windows: MAE (polyfit) = %.2f %%, MAE (Chan et al.) = %.2f %%\n', ...
        shift, mae_shift_fit(shift+1), mae_shift_lit(shift+1));
end

[best_mae_fit, best_shift_fit_idx] = min(mae_shift_fit);
[best_mae_lit, best_shift_lit_idx] = min(mae_shift_lit);
best_shift_fit = best_shift_fit_idx - 1;
best_shift_lit = best_shift_lit_idx - 1;

fprintf('Best shift (polyfit)   = %d windows (MAE = %.2f %%)\n', best_shift_fit, best_mae_fit);
fprintf('Best shift (Chan et al.) = %d windows (MAE = %.2f %%)\n', best_shift_lit, best_mae_lit);

% Apply best shifts
est_spo2_fit_shifted = nan(num_windows,1);
est_spo2_lit_shifted = nan(num_windows,1);

est_spo2_fit_shifted(1+best_shift_fit:end) = est_spo2_fit_all(1:end-best_shift_fit);
est_spo2_lit_shifted(1+best_shift_lit:end) = est_spo2_lit_all(1:end-best_shift_lit);

valid_fit_shifted_idx = ~isnan(est_spo2_fit_shifted) & ~isnan(true_spo2_all);
valid_lit_shifted_idx = ~isnan(est_spo2_lit_shifted) & ~isnan(true_spo2_all);

%% Plot: MAE vs shift for both calibrations
figure
plot(0:max_shift, mae_shift_fit, 'b-o', 'LineWidth', 1.5, 'MarkerSize', 6)
hold on
plot(0:max_shift, mae_shift_lit, 'm-s', 'LineWidth', 1.5, 'MarkerSize', 6)
xlabel('Window Shift (windows)')
ylabel('MAE SpO2 (%)')
title('SpO2 MAE vs Reference Lag Shift')
legend('Polyfit', 'Chan et al.', 'Location', 'best')
grid on

%% Plot: window vs SpO2 with best shift applied (polyfit)
figure
plot(win_ids(valid_fit_shifted_idx), true_spo2_all(valid_fit_shifted_idx), 'k-o', 'LineWidth', 1.5, 'MarkerSize', 5)
hold on
plot(win_ids(valid_fit_shifted_idx), est_spo2_fit_shifted(valid_fit_shifted_idx), 'b-s', 'LineWidth', 1.5, 'MarkerSize', 5)
xlabel('Window')
ylabel('SpO2 (%)')
title(sprintf('Window vs SpO2 (polyfit, shift=%d windows) | MAE = %.2f %%', best_shift_fit, best_mae_fit))
legend('True SpO2', 'Estimated SpO2 (polyfit, shifted)', 'Location', 'best')
grid on

%% Plot: window vs SpO2 with best shift applied (Chan et al.)
figure
plot(win_ids(valid_lit_shifted_idx), true_spo2_all(valid_lit_shifted_idx), 'k-o', 'LineWidth', 1.5, 'MarkerSize', 5)
hold on
plot(win_ids(valid_lit_shifted_idx), est_spo2_lit_shifted(valid_lit_shifted_idx), 'm-s', 'LineWidth', 1.5, 'MarkerSize', 5)
xlabel('Window')
ylabel('SpO2 (%)')
title(sprintf('Window vs SpO2 (Chan et al., shift=%d windows) | MAE = %.2f %%', best_shift_lit, best_mae_lit))
legend('True SpO2', 'Estimated SpO2 (Chan et al., shifted)', 'Location', 'best')
grid on

%% Grid plot: filtered PPG signals for selected windows
plot_win_start = 8;   % first window index to plot (1-based index into win_ids)
plot_win_end   = 23;  % last window index to plot

plot_win_end = min(plot_win_end, length(win_ids));
selected_wins = win_ids(plot_win_start:plot_win_end);
num_plot_windows = length(selected_wins);
num_cols = 4;
num_rows = ceil(num_plot_windows / num_cols);

figure

for p_idx = 1:num_plot_windows

    w_p = selected_wins(p_idx);

    idx_ppg_p = Tppg.window == w_p;
    Tw_p = Tppg(idx_ppg_p, :);

    subplot(num_rows, num_cols, p_idx)

    if height(Tw_p) < 10
        title(sprintf('W%d | no data', w_p), 'FontSize', 7)
        continue;
    end

    ir_raw_p = double(Tw_p.ir_raw);
    red_raw_p = double(Tw_p.red_raw);

    t_p = seconds(Tw_p.timestamp - Tw_p.timestamp(1));

    dt_p = seconds(diff(Tw_p.timestamp));
    dt_p = dt_p(dt_p > 0);

    if isempty(dt_p)
        title(sprintf('W%d | no data', w_p), 'FontSize', 7)
        continue;
    end

    fs_p = 1 / median(dt_p);

    ir0_p = ir_raw_p - mean(ir_raw_p);
    red0_p = red_raw_p - mean(red_raw_p);

    if length(ir0_p) <= 20 || fs_p <= 2 * 0.7
        title(sprintf('W%d | bad fs', w_p), 'FontSize', 7)
        continue;
    end

    high_cut_p = min(3.5, 0.45 * fs_p);
    [b_p, a_p] = butter(2, [0.7 high_cut_p] / (fs_p/2), 'bandpass');
    ir_f_p = filtfilt(b_p, a_p, ir0_p);
    red_f_p = filtfilt(b_p, a_p, red0_p);

    ir_n_p = ir_f_p / max(abs(ir_f_p));
    red_n_p = red_f_p / max(abs(red_f_p));

    plot(t_p, ir_n_p, 'k', 'LineWidth', 0.8)
    hold on
    plot(t_p, red_n_p, 'r', 'LineWidth', 0.8)

    R_win_p = R_all(win_all == w_p);
    k_p = find(win_ids == w_p, 1);
    spo2_true = true_spo2_all(k_p);

    if ~isempty(R_win_p) && ~isnan(spo2_true)
        title(sprintf('W%d R=%.2f SpO2=%.0f%%', w_p, R_win_p(1), spo2_true), 'FontSize', 7)
    else
        title(sprintf('W%d', w_p), 'FontSize', 7)
    end

    ylim([-1.2 1.2])
    set(gca, 'FontSize', 6, 'XTickLabel', [], 'YTickLabel', [])
    grid on
end

sgtitle(sprintf('IR (black) vs Red (red) | windows %d to %d', ...
    win_ids(plot_win_start), win_ids(plot_win_end)))
