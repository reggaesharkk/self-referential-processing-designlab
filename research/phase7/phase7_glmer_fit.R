#!/usr/bin/env Rscript

# ============================================================================
# PHASE 7 — COVARIANCE-IDENTIFIABILITY FITTER
#
# Usage:
#   Rscript phase7_glmer_fit.R input.csv output.json true_effect M1
#   Rscript phase7_glmer_fit.R input.csv output.json true_effect M2
#
# M1:
#   y ~ X + context_len + is_self
#       + (1 | item_id)
#       + (1 + is_self | model_id)
#
# M2:
#   y ~ X + context_len + is_self
#       + (1 | item_id)
#       + (1 + is_self || model_id)
#
# No adaptive optimizer switching.
# bobyqa only, matching the validated Phase-5 fitter.
# ============================================================================

suppressMessages({
  library(lme4)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 4) {
  stop(
    paste(
      "Usage: Rscript phase7_glmer_fit.R",
      "<input_csv> <output_json> <true_effect> <M1|M2>"
    )
  )
}

input_csv   <- args[1]
output_json <- args[2]
true_effect <- as.numeric(args[3])
fit_spec    <- toupper(args[4])

if (!(fit_spec %in% c("M1", "M2"))) {
  stop("fit_spec must be exactly M1 or M2")
}

dat <- read.csv(input_csv)

dat$item_id  <- factor(dat$item_id)
dat$model_id <- factor(dat$model_id)

warnings_caught <- character(0)

if (fit_spec == "M1") {

  fit_formula <- (
    y ~ X + context_len + is_self +
      (1 | item_id) +
      (1 + is_self | model_id)
  )

} else {

  fit_formula <- (
    y ~ X + context_len + is_self +
      (1 | item_id) +
      (1 + is_self || model_id)
  )
}

fit <- withCallingHandlers({

  glmer(
    fit_formula,
    data = dat,
    family = binomial(),
    control = glmerControl(
      optimizer = "bobyqa",
      optCtrl = list(maxfun = 200000)
    )
  )

}, warning = function(w) {

  warnings_caught <<- c(
    warnings_caught,
    conditionMessage(w)
  )

  invokeRestart("muffleWarning")
})

result <- list(

  fit_spec = fit_spec,

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

  model_intercept_sd = NA_real_,
  model_slope_sd = NA_real_,

  model_intercept_slope_corr = NA_real_,

  item_intercept_sd = NA_real_,

  model_cov_min_eigenvalue = NA_real_,

  theta = NULL,
  theta_lower = NULL,

  singular_component = NA_character_
)

# ============================================================================
# Singularity
# ============================================================================

result$singular <- tryCatch(
  isSingular(fit),
  error = function(e) NA
)

# ============================================================================
# Convergence
# ============================================================================

conv_failed <- FALSE

opt_msgs <- tryCatch(
  fit@optinfo$conv$lme4$messages,
  error = function(e) NULL
)

if (!is.null(opt_msgs) && length(opt_msgs) > 0) {

  result$warnings <- c(
    result$warnings,
    opt_msgs
  )

  non_singular_msgs <- opt_msgs[
    !grepl(
      "singular",
      opt_msgs,
      ignore.case = TRUE
    )
  ]

  if (length(non_singular_msgs) > 0) {
    conv_failed <- TRUE
  }
}

opt_code <- tryCatch(
  fit@optinfo$conv$opt,
  error = function(e) NA_integer_
)

if (
  !is.null(opt_code) &&
  length(opt_code) > 0 &&
  !is.na(opt_code) &&
  opt_code != 0
) {

  conv_failed <- TRUE

  result$warnings <- c(
    result$warnings,
    paste0(
      "nonzero optimizer return code: ",
      opt_code
    )
  )
}

conv_warning_pattern <- (
  "converg|gradient|Hessian|iteration limit"
)

if (
  length(warnings_caught) > 0 &&
  any(
    grepl(
      conv_warning_pattern,
      warnings_caught,
      ignore.case = TRUE
    )
  )
) {
  conv_failed <- TRUE
}

result$converged <- !conv_failed

# ============================================================================
# Fixed effect
# ============================================================================

coefs <- tryCatch(
  summary(fit)$coefficients,
  error = function(e) NULL
)

if (
  !is.null(coefs) &&
  "is_self" %in% rownames(coefs)
) {

  est <- coefs[
    "is_self",
    "Estimate"
  ]

  se <- coefs[
    "is_self",
    "Std. Error"
  ]

  pv <- coefs[
    "is_self",
    "Pr(>|z|)"
  ]

  ci_low  <- est - 1.96 * se
  ci_high <- est + 1.96 * se

  result$estimate <- unname(est)
  result$se <- unname(se)
  result$p_value <- unname(pv)

  result$ci_low <- unname(ci_low)
  result$ci_high <- unname(ci_high)

  result$rejected_at_05 <- unname(
    pv < 0.05
  )

  result$bias <- unname(
    est - true_effect
  )

  result$ci_covers_truth <- unname(
    ci_low <= true_effect &&
    true_effect <= ci_high
  )

} else {

  result$error <- (
    "is_self coefficient not found in fit summary"
  )
}

# ============================================================================
# Random-effects diagnostics
# ============================================================================

vc <- tryCatch(
  VarCorr(fit),
  error = function(e) NULL
)

if (!is.null(vc)) {

  # --------------------------------------------------------------------------
  # Item intercept
  # --------------------------------------------------------------------------

  item_vc <- tryCatch(
    vc[["item_id"]],
    error = function(e) NULL
  )

  if (!is.null(item_vc)) {

    item_sds <- attr(
      item_vc,
      "stddev"
    )

    if (
      !is.null(item_sds) &&
      "(Intercept)" %in% names(item_sds)
    ) {

      result$item_intercept_sd <- unname(
        item_sds["(Intercept)"]
      )
    }
  }

  # --------------------------------------------------------------------------
  # M1 correlated model block
  # --------------------------------------------------------------------------

  if (fit_spec == "M1") {

    model_vc <- tryCatch(
      vc[["model_id"]],
      error = function(e) NULL
    )

    if (!is.null(model_vc)) {

      m_sds <- attr(
        model_vc,
        "stddev"
      )

      m_cor <- attr(
        model_vc,
        "correlation"
      )

      if (
        !is.null(m_sds) &&
        "(Intercept)" %in% names(m_sds)
      ) {

        result$model_intercept_sd <- unname(
          m_sds["(Intercept)"]
        )
      }

      if (
        !is.null(m_sds) &&
        "is_self" %in% names(m_sds)
      ) {

        result$model_slope_sd <- unname(
          m_sds["is_self"]
        )
      }

      if (
        !is.null(m_cor) &&
        all(
          c(
            "(Intercept)",
            "is_self"
          ) %in% rownames(m_cor)
        )
      ) {

        result$model_intercept_slope_corr <- unname(
          m_cor[
            "(Intercept)",
            "is_self"
          ]
        )
      }

      eigs <- tryCatch(
        eigen(
          as.matrix(model_vc),
          symmetric = TRUE,
          only.values = TRUE
        )$values,
        error = function(e) NULL
      )

      if (!is.null(eigs)) {

        result$model_cov_min_eigenvalue <- unname(
          min(eigs)
        )
      }
    }
  }

  # --------------------------------------------------------------------------
  # M2 uncorrelated model blocks
  #
  # lme4 may represent the intercept and slope as separate grouping
  # components. We therefore identify them by their column names rather
  # than assuming one particular VarCorr list layout.
  # --------------------------------------------------------------------------

  if (fit_spec == "M2") {

    model_int_sd <- NA_real_
    model_slp_sd <- NA_real_

    for (nm in names(vc)) {

      block <- vc[[nm]]

      grp <- attr(
        block,
        "grpName"
      )

      # Depending on lme4 representation, list names may be
      # model_id / model_id.1 etc.
      is_model_block <- grepl(
        "^model_id",
        nm
      )

      if (
        !is.null(grp) &&
        length(grp) > 0
      ) {

        is_model_block <- (
          is_model_block ||
          grepl(
            "^model_id",
            grp[1]
          )
        )
      }

      if (!is_model_block) {
        next
      }

      sds <- attr(
        block,
        "stddev"
      )

      if (is.null(sds)) {
        next
      }

      if (
        "(Intercept)" %in% names(sds)
      ) {

        model_int_sd <- unname(
          sds["(Intercept)"]
        )
      }

      if (
        "is_self" %in% names(sds)
      ) {

        model_slp_sd <- unname(
          sds["is_self"]
        )
      }
    }

    result$model_intercept_sd <- model_int_sd
    result$model_slope_sd <- model_slp_sd

    # M2 does not estimate this parameter.
    result$model_intercept_slope_corr <- NA_real_

    # Under the forced-zero covariance model, the covariance
    # matrix is diagonal. Its eigenvalues are the component
    # variances.
    if (
      !is.na(model_int_sd) &&
      !is.na(model_slp_sd)
    ) {

      result$model_cov_min_eigenvalue <- min(
        model_int_sd^2,
        model_slp_sd^2
      )
    }
  }
}

# ============================================================================
# Theta diagnostics
# ============================================================================

theta_val <- tryCatch(
  getME(fit, "theta"),
  error = function(e) NULL
)

theta_low <- tryCatch(
  getME(fit, "lower"),
  error = function(e) NULL
)

if (!is.null(theta_val)) {
  result$theta <- as.numeric(
    theta_val
  )
}

if (!is.null(theta_low)) {
  result$theta_lower <- as.numeric(
    theta_low
  )
}

# ============================================================================
# Convenience singularity classification
#
# Raw diagnostics remain authoritative.
# This is only a first-match label.
# ============================================================================

if (isTRUE(result$singular)) {

  if (
    !is.na(result$model_slope_sd) &&
    result$model_slope_sd < 1e-4
  ) {

    result$singular_component <- (
      "model_slope_sd_zero"
    )

  } else if (
    fit_spec == "M1" &&
    !is.na(
      result$model_intercept_slope_corr
    ) &&
    abs(
      result$model_intercept_slope_corr
    ) > 0.999
  ) {

    result$singular_component <- (
      "model_corr_boundary"
    )

  } else if (
    !is.na(result$model_intercept_sd) &&
    result$model_intercept_sd < 1e-4
  ) {

    result$singular_component <- (
      "model_intercept_sd_zero"
    )

  } else if (
    !is.na(result$item_intercept_sd) &&
    result$item_intercept_sd < 1e-4
  ) {

    result$singular_component <- (
      "item_intercept_sd_zero"
    )

  } else {

    result$singular_component <- (
      "other_boundary"
    )
  }

} else {

  result$singular_component <- (
    "non_singular"
  )
}

write(
  toJSON(
    result,
    auto_unbox = TRUE,
    null = "null"
  ),
  file = output_json
)
