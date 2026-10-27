export const initialSatelliteSearchState = {
  products: [],
  lastSuccessfulSearch: null,
  searching: false,
  error: "",
};

/**
 * Keep the last successful product set while a later search is pending
 * or fails, and always clear a previous search error when a retry starts
 * or succeeds.
 */
export function satelliteSearchReducer(state, action) {
  switch (action.type) {
    case "start":
      return { ...state, searching: true, error: "" };

    case "success":
      return {
        products: action.products,
        lastSuccessfulSearch: action.criteria,
        searching: false,
        error: "",
      };

    case "failure":
      return {
        ...state,
        searching: false,
        error: action.message,
      };

    default:
      return state;
  }
}
