#!/usr/bin/env Rscript
### glmer_fit.R (Patched for Instrumentation & Diagnostics)
### Fits the Design Lab hierarchical logistic model on one generated
### scenario and writes fit diagnostics as JSON.
### Usage:
### Rscript glmer_fit.R <input_csv> <output_json> <true_effect>

suppressMessages({
  library(lme4)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 3) {
  stop("Usage: Rscript glmer_fit.R <input_csv> <output_json> <true_effect>")
}
input_csv   <- args[1]
output_json <- args[2]
true_effect <- as.numeric(args[3])

dat <- read.csv(input_csv)
dat$item_id  <- factor(dat$item_id)
dat$model_id <- factor(dat$model_id)

warnings_caught <- character(0)

fit <- withCallingHandlers({
  glmer(
    y ~ X + context_len + is_self + (1 | item_id) + (1 + is_self | model_id),
    data = dat,
    family = binomial(),
    control = glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 200000))
  )
}, warning = function(w) {
  warnings_caught <<- c(warnings_caught, conditionMessage(w))
  invokeRestart("muffleWarning")
})

result <- list(
  converged = NA,
  singular = FALSE,
  warnings = warnings_caught,
  estimate = NA_real_,
  se = NA_real_,
  p_value = NA_real_,
  ci_low = NA_real_,
  ci_high = NA_real_,
  rejected_at_05 = NA,
  bias = NA_real_,
  ci_covers_truth = NA,
  error = NA_character_,
  # --- Instrument / Diagnostic Fields ---
  model_intercept_sd = NA_real_,
  model_slope_sd = NA_real_,
  model_intercept_slope_corr = NA_real_,
  item_intercept_sd = NA_real_,
  model_cov_min_eigenvalue = NA_real_,
  theta = NULL,
  theta_lower = NULL,
  singular_component = NA_character_
)

result$singular <- tryCatch(isSingular(fit), error = function(e) NA)

# --- Convergence Checks ---
conv_failed <- FALSE
opt_msgs <- tryCatch(fit@optinfo$conv$lme4$messages, error = function(e) NULL)
if (!is.null(opt_msgs) && length(opt_msgs) > 0) {
  result$warnings <- c(result$warnings, opt_msgs)
  non_singular_msgs <- opt_msgs[!grepl("singular", opt_msgs, ignore.case = TRUE)]
  if (length(non_singular_msgs) > 0) {
    conv_failed <- TRUE
  }
}

opt_code <- tryCatch(fit@optinfo$conv$opt, error = function(e) NA_integer_)
if (!is.null(opt_code) && length(opt_code) > 0 && !is.na(opt_code) && opt_code != 0) {
  conv_failed <- TRUE
  result$warnings <- c(result$warnings, paste0("nonzero optimizer return code: ", opt_code))
}

conv_warning_pattern <- "converg|gradient|Hessian|iteration limit"
if (length(warnings_caught) > 0 && any(grepl(conv_warning_pattern, warnings_caught, ignore.case = TRUE))) {
  conv_failed <- TRUE
}

result$converged <- !conv_failed

# --- Extract Estimates & Wald Inference ---
coefs <- tryCatch(summary(fit)$coefficients, error = function(e) NULL)
if (!is.null(coefs) && "is_self" %in% rownames(coefs)) {
  est <- coefs["is_self", "Estimate"]
  se  <- coefs["is_self", "Std. Error"]
  pv  <- coefs["is_self", "Pr(>|z|)"]
  ci_low  <- est - 1.96 * se
  ci_high <- est + 1.96 * se
  result$estimate <- unname(est)
  result$se <- unname(se)
  result$p_value <- unname(pv)
  result$ci_low <- unname(ci_low)
  result$ci_high <- unname(ci_high)
  result$rejected_at_05 <- unname(pv < 0.05)
  result$bias <- unname(est - true_effect)
  result$ci_covers_truth <- unname(ci_low <= true_effect & true_effect <= ci_high)
} else {
  result$error <- "is_self coefficient not found in fit summary"
}

# --- Extract Detailed Random-Effects Diagnostics ---
vc <- tryCatch(VarCorr(fit), error = function(e) NULL)

if (!is.null(vc)) {
  # Item random intercept SD
  item_sd <- tryCatch(attr(vc[["item_id"]], "stddev")["(Intercept)"], error = function(e) NA_real_)
  if (!is.null(item_sd) && !is.na(item_sd)) {
    result$item_intercept_sd <- unname(item_sd)
  }

  # Model random terms
  model_vc <- tryCatch(vc[["model_id"]], error = function(e) NULL)
  if (!is.null(model_vc)) {
    m_sds <- attr(model_vc, "stddev")
    m_cor <- attr(model_vc, "correlation")

    m_int_sd <- if (!is.null(m_sds) && "(Intercept)" %in% names(m_sds)) m_sds["(Intercept)"] else NA_real_
    m_slp_sd <- if (!is.null(m_sds) && "is_self" %in% names(m_sds)) m_sds["is_self"] else NA_real_

    m_corr <- NA_real_
    if (!is.null(m_cor) && all(c("(Intercept)", "is_self") %in% rownames(m_cor))) {
      m_corr <- m_cor["(Intercept)", "is_self"]
    }

    result$model_intercept_sd <- unname(m_int_sd)
    result$model_slope_sd <- unname(m_slp_sd)
    result$model_intercept_slope_corr <- unname(m_corr)

    # Minimum eigenvalue of model random effects covariance matrix
    m_eigs <- tryCatch(eigen(model_vc)$values, error = function(e) NULL)
    if (!is.null(m_eigs)) {
      result$model_cov_min_eigenvalue <- unname(min(m_eigs))
    }
  }
}

# Relative covariance parameters (theta) and lower bounds
theta_val <- tryCatch(getME(fit, "theta"), error = function(e) NULL)
theta_low <- tryCatch(getME(fit, "lower"), error = function(e) NULL)

if (!is.null(theta_val)) {
  result$theta <- as.numeric(theta_val)
}
if (!is.null(theta_low)) {
  result$theta_lower <- as.numeric(theta_low)
}

# Singularity collapse classification
if (isTRUE(result$singular)) {
  if (!is.na(result$model_slope_sd) && result$model_slope_sd < 1e-4) {
    result$singular_component <- "model_slope_sd_zero"
  } else if (!is.na(result$model_intercept_slope_corr) && abs(result$model_intercept_slope_corr) > 0.999) {
    result$singular_component <- "model_corr_boundary"
  } else if (!is.na(result$model_intercept_sd) && result$model_intercept_sd < 1e-4) {
    result$singular_component <- "model_intercept_sd_zero"
  } else if (!is.na(result$item_intercept_sd) && result$item_intercept_sd < 1e-4) {
    result$singular_component <- "item_intercept_sd_zero"
  } else {
    result$singular_component <- "other_boundary"
  }
} else {
  result$singular_component <- "non_singular"
}

write(toJSON(result, auto_unbox = TRUE, null = "null"), file = output_json)
