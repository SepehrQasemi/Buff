const PARAM_TEXT_TYPES = new Set(["string"]);
const PARAM_INTEGER_TYPES = new Set(["integer", "int"]);
const PARAM_NUMBER_TYPES = new Set(["number", "float"]);
const PARAM_BOOLEAN_TYPES = new Set(["boolean", "bool"]);

const isObject = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);

const normalizeSchemaType = (rawType) => {
  if (Array.isArray(rawType)) {
    const first = rawType.find((value) => typeof value === "string");
    return String(first || "").toLowerCase();
  }
  return String(rawType || "").toLowerCase();
};

const getParamDefaultValue = (name, schema, defaults) => {
  if (isObject(defaults) && Object.prototype.hasOwnProperty.call(defaults, name)) {
    return defaults[name];
  }
  if (isObject(schema) && Object.prototype.hasOwnProperty.call(schema, "default")) {
    return schema.default;
  }
  return "";
};

const getStrategyParameters = (strategy) => {
  if (!strategy) {
    return [];
  }
  const schema = isObject(strategy.param_schema) ? strategy.param_schema : {};
  const properties = isObject(schema.properties) ? schema.properties : {};
  const requiredList = Array.isArray(schema.required) ? schema.required : [];
  const required = new Set(requiredList.map((value) => String(value)));

  return Object.keys(properties)
    .sort()
    .map((name) => {
      const propertySchema = isObject(properties[name]) ? properties[name] : {};
      return {
        name,
        schema: propertySchema,
        required: required.has(name),
        type: normalizeSchemaType(propertySchema.type),
        defaultValue: getParamDefaultValue(name, propertySchema, strategy.default_params),
      };
    });
};

const coerceParameterValue = (parameter, value) => {
  const type = parameter.type;
  const schema = parameter.schema;

  if (value === null || value === undefined || value === "") {
    if (parameter.required) {
      return {
        ok: false,
        error: `${parameter.name} is required.`,
      };
    }
    return { ok: true, skip: true };
  }

  if (Array.isArray(schema.enum) && schema.enum.length > 0) {
    if (!schema.enum.includes(value)) {
      return {
        ok: false,
        error: `${parameter.name} must be one of: ${schema.enum.join(", ")}`,
      };
    }
  }

  if (PARAM_BOOLEAN_TYPES.has(type)) {
    return { ok: true, value: Boolean(value) };
  }

  if (PARAM_INTEGER_TYPES.has(type)) {
    const parsed = Number.parseInt(String(value), 10);
    if (!Number.isFinite(parsed)) {
      return { ok: false, error: `${parameter.name} must be an integer.` };
    }
    if (Number.isFinite(schema.minimum) && parsed < schema.minimum) {
      return { ok: false, error: `${parameter.name} must be >= ${schema.minimum}.` };
    }
    if (Number.isFinite(schema.maximum) && parsed > schema.maximum) {
      return { ok: false, error: `${parameter.name} must be <= ${schema.maximum}.` };
    }
    return { ok: true, value: parsed };
  }

  if (PARAM_NUMBER_TYPES.has(type)) {
    const parsed = Number.parseFloat(String(value));
    if (!Number.isFinite(parsed)) {
      return { ok: false, error: `${parameter.name} must be a number.` };
    }
    if (Number.isFinite(schema.minimum) && parsed < schema.minimum) {
      return { ok: false, error: `${parameter.name} must be >= ${schema.minimum}.` };
    }
    if (Number.isFinite(schema.maximum) && parsed > schema.maximum) {
      return { ok: false, error: `${parameter.name} must be <= ${schema.maximum}.` };
    }
    return { ok: true, value: parsed };
  }

  if (PARAM_TEXT_TYPES.has(type) || !type) {
    return { ok: true, value: String(value) };
  }

  return { ok: true, value };
};

const buildRunParameters = (parameters, values) => {
  const output = {};
  for (const parameter of parameters) {
    const rawValue = values[parameter.name];
    const normalized = coerceParameterValue(parameter, rawValue);
    if (!normalized.ok) {
      return { ok: false, error: normalized.error };
    }
    if (normalized.skip) {
      continue;
    }
    output[parameter.name] = normalized.value;
  }
  return { ok: true, value: output };
};

export { buildRunParameters, coerceParameterValue, getStrategyParameters };
