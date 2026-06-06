import { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes, forwardRef, useId } from "react";

interface BaseFieldProps {
  /** label 文字（§11.1） */
  label?: ReactNode;
  /** 必填字段 — 自动加暖金小点（§11.1，不写 *） */
  required?: boolean;
  /** 帮助文字（§11.1，input 下方） */
  help?: ReactNode;
  /** 错误文字（§11.3） */
  error?: ReactNode;
}

interface InputFieldProps
  extends BaseFieldProps,
    Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  multiline?: false;
}

interface TextareaFieldProps
  extends BaseFieldProps,
    TextareaHTMLAttributes<HTMLTextAreaElement> {
  multiline: true;
}

type FormFieldProps = InputFieldProps | TextareaFieldProps;

/**
 * 表单字段（§11）：label + input/textarea + help/error。
 * - `multiline` 渲染 textarea，否则渲染 input
 * - 必填字段标 `required`，自动给 label 加暖金小点
 * - error 优先于 help 显示
 */
export const FormField = forwardRef<HTMLInputElement | HTMLTextAreaElement, FormFieldProps>(
  function FormField(props, ref) {
    const id = useId();
    const inputId = props.id ?? id;
    const {
      label,
      required,
      help,
      error,
      className: extraClassName = "",
      multiline,
      ...rest
    } = props as FormFieldProps & { id?: string };

    const labelClass = `lv-form-label${required ? " lv-form-label--required" : ""}`;
    const inputClass = multiline
      ? `lv-input lv-input--textarea ${extraClassName}`.trim()
      : `lv-input ${extraClassName}`.trim();

    return (
      <div style={{ display: "flex", flexDirection: "column" }}>
        {label && (
          <label htmlFor={inputId} className={labelClass}>
            {label}
          </label>
        )}
        {multiline ? (
          <textarea
            ref={ref as React.Ref<HTMLTextAreaElement>}
            id={inputId}
            className={inputClass}
            {...(rest as TextareaHTMLAttributes<HTMLTextAreaElement>)}
          />
        ) : (
          <input
            ref={ref as React.Ref<HTMLInputElement>}
            id={inputId}
            className={inputClass}
            {...(rest as InputHTMLAttributes<HTMLInputElement>)}
          />
        )}
        {error ? (
          <span className="lv-form-error" role="alert">{error}</span>
        ) : help ? (
          <span className="lv-form-help">{help}</span>
        ) : null}
      </div>
    );
  },
);
