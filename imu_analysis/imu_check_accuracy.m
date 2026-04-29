% run imu_find_thresholds.m first to get the stats in the proper arrays

% Constants - trimmed to only the ones we're using
BUF_SIZE = 200;
DEV_BUFFER_SIZE = 50;
CHECK_TRIGGER = 1.4;
IDLE_TRIGGER = 0.85;
ACCEL_DEV_THRESHOLD = 0.08;
GYRO_DEV_THRESHOLD = 17.1;
TILT_TRIGGER_ANGLE = 30;

% labels in group_labels array

n = length(group_labels); % expected events
num_tags = length(tags);

ECS = EVENT_CLASSIFICATION_SUMMARY;
corresponding_states = ["DETECTED_FALL" "RUNNING" "WALKING" "LIMPING" "JUMPING" "SITTING" "SQUATTING"];
legacy_tag = "JUMPING_OR_QUICK_SIT";
tag_to_state_map = [tags' corresponding_states'];

% stats
tag_stats = struct();
for i = 1:num_tags
    tag_stats.(tags(i)) = struct("NUM_TESTS", 0, "NUM_CORRECT", 0, "PERCENT_CORRECT", 0.0, "WRONG_EVENTS", []);
end

true_labels = strings(n, 1);
pred_labels = strings(n, 1);


% get calculated state vs. expected state stats using reported value
for i = 1:n
    label_idx = find(tags == group_labels(i));
    etag = group_labels(i);
    if(etag == legacy_tag)
        true_labels(i) = "";
        pred_labels(i) = "";
        continue
    end
    tag_stats.(etag).NUM_TESTS = tag_stats.(etag).NUM_TESTS + 1;

    true_labels(i) = corresponding_states(label_idx);
    pred_labels(i) = ECS(i, 1);
  
    % match!
    if(ECS(i, 1) == corresponding_states(label_idx))
        tag_stats.(etag).NUM_CORRECT = tag_stats.(etag).NUM_CORRECT + 1;
    % add misidentified events to an array
    else
        tag_stats.(etag).WRONG_EVENTS = [tag_stats.(etag).WRONG_EVENTS ECS(i,1)];
    end
end

for i = 1:num_tags
    tag_stats.(tags(i)).PERCENT_CORRECT = 100*tag_stats.(tags(i)).NUM_CORRECT / tag_stats.(tags(i)).NUM_TESTS;
    disp(tags(i));
    disp(tag_stats.(tags(i)));
end

valid_mask = true_labels ~= "";
true_labels_filt = true_labels(valid_mask);
pred_labels_filt = pred_labels(valid_mask);

% --- Confusion Matrix Figure ---
figure('Name', 'Motion Classifier Confusion Matrix', 'NumberTitle', 'off');

% Sort classes to match the order defined in corresponding_states
present_classes = intersect(corresponding_states, unique([true_labels_filt; pred_labels_filt]), 'stable');

% Convert to categoricals with explicit ordering
true_cat = categorical(true_labels_filt, present_classes);
pred_cat = categorical(pred_labels_filt, present_classes);

cm = confusionchart(true_cat, pred_cat, ...
    'Title', 'Motion Classifier Confusion Matrix', ...
    'RowSummary', 'row-normalized', ...
    'ColumnSummary', 'column-normalized');

%% 
num_classes = length(present_classes);
TP = zeros(num_classes, 1);
TN = zeros(num_classes, 1);
FP = zeros(num_classes, 1);
FN = zeros(num_classes, 1);

for i = 1:num_classes
    cls = present_classes(i);
    TP(i) = sum(true_labels_filt == cls & pred_labels_filt == cls);
    TN(i) = sum(true_labels_filt ~= cls & pred_labels_filt ~= cls);
    FP(i) = sum(true_labels_filt ~= cls & pred_labels_filt == cls);
    FN(i) = sum(true_labels_filt == cls & pred_labels_filt ~= cls);
end

summary_table = table(present_classes(:), TP, TN, FP, FN, ...
    'VariableNames', {'Class', 'TP', 'TN', 'FP', 'FN'});

disp('--- Per-Class TP/TN/FP/FN Summary ---');
disp(summary_table);

overall_TP = sum(TP);
overall_TN = sum(TN);
overall_FP = sum(FP);
overall_FN = sum(FN);

fprintf('\n--- Overall Classifier Summary ---\n');
fprintf('TP: %d\n', overall_TP);
fprintf('TN: %d\n', overall_TN);
fprintf('FP: %d\n', overall_FP);
fprintf('FN: %d\n', overall_FN);
fprintf('TP RATE: %.4f\n', 100*(overall_TP / (overall_TP + overall_FN)));
fprintf('TN RATE: %.4f\n', 100*(overall_TN / (overall_FP + overall_TN)));
fprintf('FP RATE: %.4f\n', 100*(overall_FP / (overall_FP + overall_TN)));
fprintf('FN RATE: %.4f\n', 100*(overall_FN / (overall_FN + overall_TP)));
